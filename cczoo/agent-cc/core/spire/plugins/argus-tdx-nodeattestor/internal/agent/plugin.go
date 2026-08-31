// Package agent implements the SPIRE Agent side of Argus TDX Node Attestation.
// It proves possession of the configured Agent key and obtains a fresh Quote;
// Quote appraisal and Agent admission remain on the Server side.
package agent

import (
	"context"
	"crypto/ed25519"
	"strings"
	"sync"
	"time"

	"github.com/hashicorp/go-hclog"
	nodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/evidence"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/telemetry"
	"github.com/spiffe/spire-plugin-sdk/pluginsdk"
	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/agent/nodeattestor/v1"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

var _ pluginsdk.NeedsLogger = (*Plugin)(nil)
var _ pluginsdk.NeedsHostServices = (*Plugin)(nil)

type EvidenceProvider interface {
	// GetNodeEvidence returns a raw TDX Quote bound to the nonce and proof key.
	GetNodeEvidence(context.Context, []byte, []byte) ([]byte, error)
}

// ProviderFactory constructs the guest-local Evidence Provider client from the
// immutable SPIRE plugin configuration.
type ProviderFactory func(*Config) (EvidenceProvider, error)

// Plugin implements SPIRE's Agent NodeAttestor protocol for the argus_tdx type.
type Plugin struct {
	nodeattestorapi.UnimplementedNodeAttestorServer
	configapi.UnimplementedConfigServer

	configMu sync.RWMutex
	config   *Config
	logger   hclog.Logger

	keyLoader       func(string) (ed25519.PrivateKey, error)
	providerFactory ProviderFactory
	telemetry       telemetry.Recorder
}

// New returns an unconfigured Agent NodeAttestor.
func New() *Plugin {
	return &Plugin{
		keyLoader: loadProofKey,
		providerFactory: func(config *Config) (EvidenceProvider, error) {
			return evidence.NewClient(config.EvidenceSocketPath, config.EvidenceTimeout, config.MaxQuoteBytes)
		},
	}
}

// AidAttestation answers one Server challenge with a Quote and proof-of-possession
// signature from the same key that is bound into TDX REPORTDATA.
func (plugin *Plugin) AidAttestation(stream nodeattestorapi.NodeAttestor_AidAttestationServer) (err error) {
	started := time.Now()
	defer func() { plugin.telemetry.Attestation("agent", started, err) }()
	config, err := plugin.getConfig()
	if err != nil {
		return err
	}
	privateKey, err := plugin.keyLoader(config.ProofKeyPath)
	if err != nil {
		return status.Errorf(codes.Internal, "load proof key: %v", err)
	}
	publicKey := privateKey.Public().(ed25519.PublicKey)

	// The initial payload identifies the pre-provisioned Agent slot. It does not
	// grant an identity until the Server verifies the complete attestation.
	hello := &nodeattestor.AgentHello{ProofPublicKey: publicKey}
	if err := protocol.ValidateAgentHello(hello); err != nil {
		return status.Errorf(codes.Internal, "construct AgentHello: %v", err)
	}
	helloBytes, err := (proto.MarshalOptions{Deterministic: true}).Marshal(hello)
	if err != nil {
		return status.Errorf(codes.Internal, "marshal AgentHello: %v", err)
	}
	if err := stream.Send(&nodeattestorapi.PayloadOrChallengeResponse{
		Data: &nodeattestorapi.PayloadOrChallengeResponse_Payload{Payload: helloBytes},
	}); err != nil {
		return status.Errorf(codes.Unavailable, "send AgentHello: %v", err)
	}

	spireChallenge, err := stream.Recv()
	if err != nil {
		return status.Errorf(codes.Unavailable, "receive NodeChallenge: %v", err)
	}
	if len(spireChallenge.Challenge) == 0 || len(spireChallenge.Challenge) > protocol.MaxChallengeSize {
		return status.Error(codes.InvalidArgument, "NodeChallenge size is outside the allowed range")
	}
	challenge := new(nodeattestor.NodeChallenge)
	if err := proto.Unmarshal(spireChallenge.Challenge, challenge); err != nil {
		return status.Errorf(codes.InvalidArgument, "unmarshal NodeChallenge: %v", err)
	}
	if err := protocol.ValidateNodeChallenge(challenge); err != nil {
		return status.Errorf(codes.InvalidArgument, "validate NodeChallenge: %v", err)
	}

	provider, err := plugin.providerFactory(config)
	if err != nil {
		return status.Errorf(codes.Internal, "configure Evidence Provider client: %v", err)
	}
	evidenceContext, cancel := context.WithTimeout(stream.Context(), config.EvidenceTimeout)
	defer cancel()
	// The Provider creates hardware evidence only; it does not decide whether
	// the Quote or the requested Agent identity is trusted.
	quote, err := provider.GetNodeEvidence(evidenceContext, challenge.Nonce, publicKey)
	if err != nil {
		return status.Errorf(codes.Unavailable, "obtain node evidence: %v", err)
	}
	plugin.telemetry.EvidenceBytes("agent", len(quote))
	if len(quote) == 0 || int64(len(quote)) > config.MaxQuoteBytes {
		return status.Error(codes.ResourceExhausted, "TDX Quote size is outside the allowed range")
	}
	digest, err := protocol.TranscriptDigest(publicKey, challenge.Nonce, challenge.ExpiresAtUnixMs, quote)
	if err != nil {
		return status.Errorf(codes.InvalidArgument, "construct transcript: %v", err)
	}
	// The signature proves that the key bound into REPORTDATA also approved this
	// exact Quote, challenge nonce, and challenge expiry.
	response := &nodeattestor.NodeEvidenceResponse{
		TdxQuote:            quote,
		TranscriptSignature: ed25519.Sign(privateKey, digest[:]),
	}
	if err := protocol.ValidateNodeEvidenceResponse(response, config.MaxQuoteBytes); err != nil {
		return status.Errorf(codes.InvalidArgument, "construct NodeEvidenceResponse: %v", err)
	}
	responseBytes, err := (proto.MarshalOptions{Deterministic: true}).Marshal(response)
	if err != nil {
		return status.Errorf(codes.Internal, "marshal NodeEvidenceResponse: %v", err)
	}
	if err := stream.Send(&nodeattestorapi.PayloadOrChallengeResponse{
		Data: &nodeattestorapi.PayloadOrChallengeResponse_ChallengeResponse{ChallengeResponse: responseBytes},
	}); err != nil {
		return status.Errorf(codes.Unavailable, "send NodeEvidenceResponse: %v", err)
	}
	return nil
}

func (plugin *Plugin) Validate(_ context.Context, request *configapi.ValidateRequest) (*configapi.ValidateResponse, error) {
	if request == nil {
		return &configapi.ValidateResponse{Valid: false, Notes: []string{"request is required"}}, nil
	}
	_, notes := parseConfig(request.CoreConfiguration, request.HclConfiguration)
	return &configapi.ValidateResponse{Valid: len(notes) == 0, Notes: notes}, nil
}

func (plugin *Plugin) Configure(_ context.Context, request *configapi.ConfigureRequest) (*configapi.ConfigureResponse, error) {
	if request == nil {
		return nil, status.Error(codes.InvalidArgument, "request is required")
	}
	config, notes := parseConfig(request.CoreConfiguration, request.HclConfiguration)
	if len(notes) > 0 {
		return nil, status.Errorf(codes.InvalidArgument, "invalid configuration: %s", strings.Join(notes, "; "))
	}
	plugin.configMu.Lock()
	plugin.config = config
	plugin.configMu.Unlock()
	return &configapi.ConfigureResponse{}, nil
}

func (plugin *Plugin) BrokerHostServices(broker pluginsdk.ServiceBroker) error {
	plugin.telemetry.Broker(broker)
	return nil
}

func (plugin *Plugin) SetLogger(logger hclog.Logger) {
	plugin.logger = logger
}

func (plugin *Plugin) getConfig() (*Config, error) {
	plugin.configMu.RLock()
	defer plugin.configMu.RUnlock()
	if plugin.config == nil {
		return nil, status.Error(codes.FailedPrecondition, "plugin is not configured")
	}
	return plugin.config, nil
}

func (plugin *Plugin) String() string {
	return "argus_tdx Agent NodeAttestor"
}
