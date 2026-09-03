// Package server implements the SPIRE Server side of Argus TDX Node
// Attestation. It binds a fixed Agent slot to a proof key and delegates Quote
// appraisal to the configured Trustee.
package server

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"io"
	"strings"
	"sync"
	"time"

	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/server/nodeattestor/v1"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"

	argusnodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/trustee"
)

// TrusteeVerifier appraises a raw Quote against the Node runtime data supplied
// by this protocol.
type TrusteeVerifier interface {
	VerifyNode(context.Context, trustee.VerifyInput) (trustee.VerifiedNodeClaims, error)
}

// VerifierFactory constructs the Trustee client from validated startup config.
type VerifierFactory func(*Config) (TrusteeVerifier, error)

type runtimeState struct {
	config   *Config
	verifier TrusteeVerifier
}

// Plugin implements SPIRE's Server NodeAttestor protocol for the argus_tdx type.
type Plugin struct {
	nodeattestorapi.UnimplementedNodeAttestorServer
	configapi.UnimplementedConfigServer

	stateMu sync.RWMutex
	state   *runtimeState

	random          io.Reader
	now             func() time.Time
	verifierFactory VerifierFactory
}

// New returns an unconfigured Server NodeAttestor.
func New() *Plugin {
	return &Plugin{
		random: rand.Reader,
		now:    time.Now,
		verifierFactory: func(config *Config) (TrusteeVerifier, error) {
			return trustee.NewClient(
				config.TrusteeURL,
				config.TrusteeTLSConfig,
				config.EARPublicKey,
				config.EARExpectedIssuer,
				config.EARExpectedProfile,
				config.PolicyID,
				config.TrusteeTimeout,
				config.MaxTrusteeResponseBytes,
			)
		},
	}
}

// Attest authenticates one Agent through key pinning, proof-of-possession, and
// Trustee appraisal before returning SPIRE Agent attributes.
func (plugin *Plugin) Attest(stream nodeattestorapi.NodeAttestor_AttestServer) error {
	state, err := plugin.getState()
	if err != nil {
		return err
	}
	initial, err := stream.Recv()
	if err != nil {
		return status.Errorf(codes.Unavailable, "receive AgentHello: %v", err)
	}
	if len(initial.GetPayload()) == 0 || len(initial.GetChallengeResponse()) != 0 || len(initial.GetPayload()) > protocol.MaxAgentHelloSize {
		return status.Error(codes.InvalidArgument, "first attestation request must contain only AgentHello")
	}
	hello := new(argusnodeattestor.AgentHello)
	if err := proto.Unmarshal(initial.GetPayload(), hello); err != nil {
		return status.Errorf(codes.InvalidArgument, "unmarshal AgentHello: %v", err)
	}
	if len(hello.ProtoReflect().GetUnknown()) != 0 {
		return status.Error(codes.InvalidArgument, "AgentHello contains unknown fields")
	}
	if err := protocol.ValidateAgentHello(hello); err != nil {
		return status.Errorf(codes.InvalidArgument, "validate AgentHello: %v", err)
	}
	// REPORTDATA can bind any supplied key. The independent slot pin limits this
	// fixed Agent identity to the operator-provisioned proof key.
	keyDigest := sha256.Sum256(hello.ProofPublicKey)
	if keyDigest != state.config.SlotOwnerKeySHA256 {
		return status.Error(codes.PermissionDenied, "proof public key does not match the fixed Agent slot")
	}

	// A fresh Server nonce makes each accepted Quote specific to this stream.
	nonce := make([]byte, protocol.NonceSize)
	if _, err := io.ReadFull(plugin.random, nonce); err != nil {
		return status.Errorf(codes.Internal, "generate challenge nonce: %v", err)
	}
	expiresAtUnixMs := uint64(plugin.now().Add(state.config.ChallengeTTL).UnixMilli())
	challenge := &argusnodeattestor.NodeChallenge{Nonce: nonce, ExpiresAtUnixMs: expiresAtUnixMs}
	challengeBytes, err := proto.Marshal(challenge)
	if err != nil {
		return status.Errorf(codes.Internal, "marshal NodeChallenge: %v", err)
	}
	if err := stream.Send(&nodeattestorapi.AttestResponse{
		Response: &nodeattestorapi.AttestResponse_Challenge{Challenge: challengeBytes},
	}); err != nil {
		return status.Errorf(codes.Unavailable, "send NodeChallenge: %v", err)
	}

	request, err := stream.Recv()
	if err != nil {
		return status.Errorf(codes.Unavailable, "receive NodeEvidenceResponse: %v", err)
	}
	if len(request.GetChallengeResponse()) == 0 || len(request.GetPayload()) != 0 || len(request.GetChallengeResponse()) > protocol.MaxNodeEvidenceResponseSize {
		return status.Error(codes.InvalidArgument, "second attestation request must contain only NodeEvidenceResponse")
	}
	response := new(argusnodeattestor.NodeEvidenceResponse)
	if err := proto.Unmarshal(request.GetChallengeResponse(), response); err != nil {
		return status.Errorf(codes.InvalidArgument, "unmarshal NodeEvidenceResponse: %v", err)
	}
	if len(response.ProtoReflect().GetUnknown()) != 0 {
		return status.Error(codes.InvalidArgument, "NodeEvidenceResponse contains unknown fields")
	}
	if err := protocol.ValidateNodeEvidenceResponse(response, state.config.MaxQuoteBytes); err != nil {
		return status.Errorf(codes.InvalidArgument, "validate NodeEvidenceResponse: %v", err)
	}
	if uint64(plugin.now().UnixMilli()) >= expiresAtUnixMs {
		return status.Error(codes.PermissionDenied, "NodeChallenge expired")
	}
	// Verify proof-of-possession before invoking the remote appraisal service.
	transcriptDigest, err := protocol.TranscriptDigest(hello.ProofPublicKey, nonce, expiresAtUnixMs, response.TdxQuote)
	if err != nil {
		return status.Errorf(codes.InvalidArgument, "construct transcript: %v", err)
	}
	if !ed25519.Verify(ed25519.PublicKey(hello.ProofPublicKey), transcriptDigest[:], response.TranscriptSignature) {
		return status.Error(codes.PermissionDenied, "transcript signature verification failed")
	}
	runtimeData, err := protocol.NodeRuntimeData(nonce, hello.ProofPublicKey)
	if err != nil {
		return status.Errorf(codes.Internal, "construct node runtime data: %v", err)
	}

	verifyContext, cancel := context.WithTimeout(stream.Context(), state.config.TrusteeTimeout)
	defer cancel()
	// Trustee owns Quote, collateral, TCB, and policy appraisal. The plugin
	// supplies the same canonical runtime data used by the guest Provider.
	if _, err := state.verifier.VerifyNode(verifyContext, trustee.VerifyInput{
		Quote: response.TdxQuote, RuntimeData: runtimeData,
	}); err != nil {
		return status.Errorf(codes.PermissionDenied, "Trustee verification failed: %v", err)
	}
	if uint64(plugin.now().UnixMilli()) >= expiresAtUnixMs {
		return status.Error(codes.PermissionDenied, "NodeChallenge expired during Trustee verification")
	}
	// AgentAttributes admit the Agent to SPIRE. The SPIRE Server CA, not this
	// plugin or Trustee, subsequently issues the Agent SVID.
	if err := stream.Send(&nodeattestorapi.AttestResponse{
		Response: &nodeattestorapi.AttestResponse_AgentAttributes{AgentAttributes: &nodeattestorapi.AgentAttributes{
			SpiffeId:       protocol.FixedAgentSPIFFEID,
			SelectorValues: nil,
			// Re-attestation repeats the full fresh-nonce Quote and Trustee flow.
			CanReattest: true,
		}},
	}); err != nil {
		return status.Errorf(codes.Unavailable, "send AgentAttributes: %v", err)
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
	verifier, err := plugin.verifierFactory(config)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "configure Trustee verifier: %v", err)
	}
	plugin.stateMu.Lock()
	plugin.state = &runtimeState{config: config, verifier: verifier}
	plugin.stateMu.Unlock()
	return &configapi.ConfigureResponse{}, nil
}

func (plugin *Plugin) getState() (*runtimeState, error) {
	plugin.stateMu.RLock()
	defer plugin.stateMu.RUnlock()
	if plugin.state == nil {
		return nil, status.Error(codes.FailedPrecondition, "plugin is not configured")
	}
	return plugin.state, nil
}
