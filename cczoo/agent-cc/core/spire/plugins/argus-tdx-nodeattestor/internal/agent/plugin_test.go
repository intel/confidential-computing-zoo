package agent

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"fmt"
	"testing"
	"time"

	nodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/agent/nodeattestor/v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/proto"
)

type fakeProvider struct {
	nonce     []byte
	publicKey []byte
	quote     []byte
	calls     int
}

func (provider *fakeProvider) GetNodeEvidence(_ context.Context, nonce, publicKey []byte) ([]byte, error) {
	provider.calls++
	provider.nonce = append([]byte(nil), nonce...)
	provider.publicKey = append([]byte(nil), publicKey...)
	return append([]byte(nil), provider.quote...), nil
}

type fakeAidStream struct {
	context   context.Context
	challenge *nodeattestorapi.Challenge
	sent      []*nodeattestorapi.PayloadOrChallengeResponse
}

func (stream *fakeAidStream) Send(response *nodeattestorapi.PayloadOrChallengeResponse) error {
	stream.sent = append(stream.sent, response)
	return nil
}

func (stream *fakeAidStream) Recv() (*nodeattestorapi.Challenge, error) {
	if len(stream.sent) != 1 || len(stream.sent[0].GetPayload()) == 0 {
		return nil, fmt.Errorf("AgentHello was not sent before receiving challenge")
	}
	return stream.challenge, nil
}

func (stream *fakeAidStream) SetHeader(metadata.MD) error  { return nil }
func (stream *fakeAidStream) SendHeader(metadata.MD) error { return nil }
func (stream *fakeAidStream) SetTrailer(metadata.MD)       {}
func (stream *fakeAidStream) Context() context.Context     { return stream.context }
func (stream *fakeAidStream) SendMsg(any) error            { return nil }
func (stream *fakeAidStream) RecvMsg(any) error            { return nil }

func TestAidAttestationSendsHelloAndSignedQuote(t *testing.T) {
	privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x41}, ed25519.SeedSize))
	publicKey := privateKey.Public().(ed25519.PublicKey)
	nonce := bytes.Repeat([]byte{0x22}, protocol.NonceSize)
	expiresAt := uint64(time.Now().Add(30 * time.Second).UnixMilli())
	challengeBytes, err := proto.Marshal(&nodeattestor.NodeChallenge{Nonce: nonce, ExpiresAtUnixMs: expiresAt})
	if err != nil {
		t.Fatal(err)
	}

	provider := &fakeProvider{quote: []byte{0x54, 0x44, 0x58}}
	plugin := New()
	plugin.config = &Config{
		EvidenceSocketPath: "/run/argus/evidence-provider.sock",
		ProofKeyPath:       "/not/read/by-test",
		EvidenceTimeout:    time.Second,
		MaxQuoteBytes:      protocol.MaxQuoteSize,
	}
	plugin.keyLoader = func(string) (ed25519.PrivateKey, error) { return privateKey, nil }
	plugin.providerFactory = func(*Config) (EvidenceProvider, error) { return provider, nil }
	stream := &fakeAidStream{
		context:   context.Background(),
		challenge: &nodeattestorapi.Challenge{Challenge: challengeBytes},
	}

	if err := plugin.AidAttestation(stream); err != nil {
		t.Fatal(err)
	}
	if len(stream.sent) != 2 {
		t.Fatalf("sent message count = %d, want 2", len(stream.sent))
	}
	hello := new(nodeattestor.AgentHello)
	if err := proto.Unmarshal(stream.sent[0].GetPayload(), hello); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(hello.ProofPublicKey, publicKey) {
		t.Fatal("AgentHello proof public key mismatch")
	}
	if provider.calls != 1 || !bytes.Equal(provider.nonce, nonce) || !bytes.Equal(provider.publicKey, publicKey) {
		t.Fatal("Evidence Provider did not receive the current nonce and proof public key")
	}

	response := new(nodeattestor.NodeEvidenceResponse)
	if err := proto.Unmarshal(stream.sent[1].GetChallengeResponse(), response); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(response.TdxQuote, provider.quote) {
		t.Fatal("NodeEvidenceResponse Quote mismatch")
	}
	digest, err := protocol.TranscriptDigest(publicKey, nonce, expiresAt, provider.quote)
	if err != nil {
		t.Fatal(err)
	}
	if !ed25519.Verify(publicKey, digest[:], response.TranscriptSignature) {
		t.Fatal("NodeEvidenceResponse transcript signature is invalid")
	}
}

func TestAidAttestationRejectsExpiredChallengeBeforeCallingProvider(t *testing.T) {
	privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x41}, ed25519.SeedSize))
	challengeBytes, err := proto.Marshal(&nodeattestor.NodeChallenge{
		Nonce:           make([]byte, protocol.NonceSize),
		ExpiresAtUnixMs: uint64(time.Now().Add(-time.Second).UnixMilli()),
	})
	if err != nil {
		t.Fatal(err)
	}
	provider := &fakeProvider{quote: []byte{1}}
	plugin := New()
	plugin.config = &Config{ProofKeyPath: "/unused", EvidenceTimeout: time.Second, MaxQuoteBytes: protocol.MaxQuoteSize}
	plugin.keyLoader = func(string) (ed25519.PrivateKey, error) { return privateKey, nil }
	plugin.providerFactory = func(*Config) (EvidenceProvider, error) { return provider, nil }
	stream := &fakeAidStream{context: context.Background(), challenge: &nodeattestorapi.Challenge{Challenge: challengeBytes}}

	if err := plugin.AidAttestation(stream); err == nil {
		t.Fatal("expired NodeChallenge was accepted")
	}
	if provider.calls != 0 {
		t.Fatal("Evidence Provider was called for an expired challenge")
	}
}

var _ nodeattestorapi.NodeAttestor_AidAttestationServer = (*fakeAidStream)(nil)
