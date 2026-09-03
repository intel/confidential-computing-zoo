package agent

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"sync"
	"testing"
	"time"

	nodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	"github.com/spiffe/spire-plugin-sdk/pluginsdk"
	"github.com/spiffe/spire-plugin-sdk/plugintest"
	metricsapi "github.com/spiffe/spire-plugin-sdk/proto/spire/hostservice/common/metrics/v1"
	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/agent/nodeattestor/v1"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/emptypb"
)

type contractMetrics struct {
	metricsapi.UnimplementedMetricsServer
	mu        sync.Mutex
	counters  []*metricsapi.IncrCounterRequest
	samples   []*metricsapi.AddSampleRequest
	durations []*metricsapi.MeasureSinceRequest
}

func (metrics *contractMetrics) IncrCounter(_ context.Context, request *metricsapi.IncrCounterRequest) (*emptypb.Empty, error) {
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	metrics.counters = append(metrics.counters, request)
	return &emptypb.Empty{}, nil
}

func (metrics *contractMetrics) AddSample(_ context.Context, request *metricsapi.AddSampleRequest) (*emptypb.Empty, error) {
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	metrics.samples = append(metrics.samples, request)
	return &emptypb.Empty{}, nil
}

func (metrics *contractMetrics) MeasureSince(_ context.Context, request *metricsapi.MeasureSinceRequest) (*emptypb.Empty, error) {
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	metrics.durations = append(metrics.durations, request)
	return &emptypb.Empty{}, nil
}

func TestPluginSDKContractSendsInitialPayloadFirst(t *testing.T) {
	privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x51}, ed25519.SeedSize))
	provider := &fakeProvider{quote: []byte{0x54, 0x44, 0x58}}
	plugin := New()
	metrics := new(contractMetrics)
	plugin.keyLoader = func(string) (ed25519.PrivateKey, error) { return privateKey, nil }
	plugin.providerFactory = func(*Config) (EvidenceProvider, error) { return provider, nil }

	nodeAttestorClient := new(nodeattestorapi.NodeAttestorPluginClient)
	configClient := new(configapi.ConfigServiceClient)
	plugintest.ServeInBackground(t, plugintest.Config{
		PluginServer: nodeattestorapi.NodeAttestorPluginServer(plugin),
		PluginClient: nodeAttestorClient,
		ServiceServers: []pluginsdk.ServiceServer{
			configapi.ConfigServiceServer(plugin),
		},
		ServiceClients:     []pluginsdk.ServiceClient{configClient},
		HostServiceServers: []pluginsdk.ServiceServer{metricsapi.MetricsServiceServer(metrics)},
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	validation, err := configClient.Validate(ctx, &configapi.ValidateRequest{HclConfiguration: validAgentConfig})
	if err != nil {
		t.Fatal(err)
	}
	if !validation.Valid || len(validation.Notes) != 0 {
		t.Fatalf("validation = %#v", validation)
	}
	if _, err := configClient.Configure(ctx, &configapi.ConfigureRequest{HclConfiguration: validAgentConfig}); err != nil {
		t.Fatal(err)
	}

	stream, err := nodeAttestorClient.AidAttestation(ctx)
	if err != nil {
		t.Fatal(err)
	}
	initial, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if len(initial.GetPayload()) == 0 || len(initial.GetChallengeResponse()) != 0 {
		t.Fatal("first Agent message was not an initial payload")
	}
	hello := new(nodeattestor.AgentHello)
	if err := proto.Unmarshal(initial.GetPayload(), hello); err != nil {
		t.Fatal(err)
	}
	nonce := bytes.Repeat([]byte{0x71}, protocol.NonceSize)
	challengeBytes, err := proto.Marshal(&nodeattestor.NodeChallenge{
		Nonce:           nonce,
		ExpiresAtUnixMs: uint64(time.Now().Add(30 * time.Second).UnixMilli()),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(&nodeattestorapi.Challenge{Challenge: challengeBytes}); err != nil {
		t.Fatal(err)
	}
	final, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if len(final.GetChallengeResponse()) == 0 || len(final.GetPayload()) != 0 {
		t.Fatal("second Agent message was not a challenge response")
	}
	if _, err := stream.Recv(); err == nil {
		t.Fatal("Agent stream returned more than one challenge response")
	}
	metrics.mu.Lock()
	defer metrics.mu.Unlock()
	if len(metrics.counters) != 1 || len(metrics.samples) != 1 || len(metrics.durations) != 1 {
		t.Fatalf("metrics calls = counters:%d samples:%d durations:%d", len(metrics.counters), len(metrics.samples), len(metrics.durations))
	}
	if metrics.samples[0].Val != float32(len(provider.quote)) {
		t.Fatalf("Quote bytes = %v", metrics.samples[0].Val)
	}
}
