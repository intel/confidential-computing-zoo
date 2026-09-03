package server

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"fmt"
	"io"
	"testing"
	"time"

	nodeattestorapi "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/server/nodeattestor/v1"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/proto"

	argusnodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/trustee"
)

type fakeVerifier struct {
	called bool
	input  trustee.VerifyInput
	err    error
	hook   func()
}

func (verifier *fakeVerifier) VerifyNode(_ context.Context, input trustee.VerifyInput) (trustee.VerifiedNodeClaims, error) {
	verifier.called = true
	verifier.input = input
	if verifier.hook != nil {
		verifier.hook()
	}
	return trustee.VerifiedNodeClaims{}, verifier.err
}

type fakeAttestStream struct {
	context       context.Context
	helloPayload  []byte
	privateKey    ed25519.PrivateKey
	quote         []byte
	badSignature  bool
	unknownFields bool
	receiveCount  int
	sentResponses []*nodeattestorapi.AttestResponse
}

func (stream *fakeAttestStream) Recv() (*nodeattestorapi.AttestRequest, error) {
	stream.receiveCount++
	if stream.receiveCount == 1 {
		return &nodeattestorapi.AttestRequest{Request: &nodeattestorapi.AttestRequest_Payload{Payload: stream.helloPayload}}, nil
	}
	if stream.receiveCount != 2 || len(stream.sentResponses) != 1 {
		return nil, fmt.Errorf("unexpected receive sequence")
	}
	challenge := new(argusnodeattestor.NodeChallenge)
	if err := proto.Unmarshal(stream.sentResponses[0].GetChallenge(), challenge); err != nil {
		return nil, err
	}
	publicKey := stream.privateKey.Public().(ed25519.PublicKey)
	digest, err := protocol.TranscriptDigest(publicKey, challenge.Nonce, challenge.ExpiresAtUnixMs, stream.quote)
	if err != nil {
		return nil, err
	}
	signature := ed25519.Sign(stream.privateKey, digest[:])
	if stream.badSignature {
		signature[0] ^= 0xff
	}
	responseBytes, err := proto.Marshal(&argusnodeattestor.NodeEvidenceResponse{
		TdxQuote: stream.quote, TranscriptSignature: signature,
	})
	if err != nil {
		return nil, err
	}
	if stream.unknownFields {
		responseBytes = append(responseBytes, 0x98, 0x06, 0x01)
	}
	return &nodeattestorapi.AttestRequest{Request: &nodeattestorapi.AttestRequest_ChallengeResponse{ChallengeResponse: responseBytes}}, nil
}

func (stream *fakeAttestStream) Send(response *nodeattestorapi.AttestResponse) error {
	stream.sentResponses = append(stream.sentResponses, response)
	return nil
}

func (stream *fakeAttestStream) SetHeader(metadata.MD) error  { return nil }
func (stream *fakeAttestStream) SendHeader(metadata.MD) error { return nil }
func (stream *fakeAttestStream) SetTrailer(metadata.MD)       {}
func (stream *fakeAttestStream) Context() context.Context     { return stream.context }
func (stream *fakeAttestStream) SendMsg(any) error            { return nil }
func (stream *fakeAttestStream) RecvMsg(any) error            { return nil }

func TestAttestPinsKeyVerifiesPoPAndReturnsFixedAttributes(t *testing.T) {
	plugin, stream, verifier, _ := configuredAttestation(t)
	if err := plugin.Attest(stream); err != nil {
		t.Fatal(err)
	}
	if !verifier.called {
		t.Fatal("Trustee verifier was not called")
	}
	challenge := new(argusnodeattestor.NodeChallenge)
	if err := proto.Unmarshal(stream.sentResponses[0].GetChallenge(), challenge); err != nil {
		t.Fatal(err)
	}
	expectedRuntimeData, err := protocol.NodeRuntimeData(challenge.Nonce, stream.privateKey.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(verifier.input.Quote, stream.quote) || !bytes.Equal(verifier.input.RuntimeData, expectedRuntimeData) {
		t.Fatalf("Trustee input = %#v", verifier.input)
	}
	attributes := stream.sentResponses[1].GetAgentAttributes()
	if attributes == nil || attributes.SpiffeId != protocol.FixedAgentSPIFFEID || len(attributes.SelectorValues) != 0 || !attributes.CanReattest {
		t.Fatalf("AgentAttributes = %#v", attributes)
	}
}

func TestAttestRejectsUnpinnedKeyBeforeGeneratingChallenge(t *testing.T) {
	plugin, stream, verifier, _ := configuredAttestation(t)
	plugin.state.config.SlotOwnerKeySHA256 = [sha256.Size]byte{}
	plugin.random = failingReader{}
	if err := plugin.Attest(stream); err == nil {
		t.Fatal("unpinned proof key was accepted")
	}
	if verifier.called || len(stream.sentResponses) != 0 {
		t.Fatal("challenge or Trustee call occurred before the static pin matched")
	}
}

func TestAttestRejectsUnknownHelloFields(t *testing.T) {
	plugin, stream, verifier, _ := configuredAttestation(t)
	stream.helloPayload = append(stream.helloPayload, 0x98, 0x06, 0x01)
	if err := plugin.Attest(stream); err == nil {
		t.Fatal("AgentHello with unknown fields was accepted")
	}
	if verifier.called || len(stream.sentResponses) != 0 {
		t.Fatal("unknown AgentHello reached challenge or Trustee")
	}
}

func TestAttestRejectsBadPoPBeforeTrustee(t *testing.T) {
	plugin, stream, verifier, _ := configuredAttestation(t)
	stream.badSignature = true
	if err := plugin.Attest(stream); err == nil {
		t.Fatal("bad transcript signature was accepted")
	}
	if verifier.called || len(stream.sentResponses) != 1 {
		t.Fatal("Trustee or AgentAttributes was reached after bad PoP")
	}
}

func TestAttestRejectsUnknownResponseFields(t *testing.T) {
	plugin, stream, verifier, _ := configuredAttestation(t)
	stream.unknownFields = true
	if err := plugin.Attest(stream); err == nil {
		t.Fatal("NodeEvidenceResponse with unknown fields was accepted")
	}
	if verifier.called || len(stream.sentResponses) != 1 {
		t.Fatal("unknown NodeEvidenceResponse reached Trustee or AgentAttributes")
	}
}

func TestAttestRechecksChallengeExpiryAfterTrustee(t *testing.T) {
	plugin, stream, verifier, currentTime := configuredAttestation(t)
	verifier.hook = func() { *currentTime = currentTime.Add(plugin.state.config.ChallengeTTL) }
	if err := plugin.Attest(stream); err == nil {
		t.Fatal("attestation completing at challenge expiry was accepted")
	}
	if !verifier.called || len(stream.sentResponses) != 1 {
		t.Fatal("expired appraisal returned AgentAttributes")
	}
}

func configuredAttestation(t *testing.T) (*Plugin, *fakeAttestStream, *fakeVerifier, *time.Time) {
	t.Helper()
	privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x41}, ed25519.SeedSize))
	publicKey := privateKey.Public().(ed25519.PublicKey)
	helloBytes, err := proto.Marshal(&argusnodeattestor.AgentHello{ProofPublicKey: publicKey})
	if err != nil {
		t.Fatal(err)
	}
	keyDigest := sha256.Sum256(publicKey)
	verifier := new(fakeVerifier)
	currentTime := time.Now().UTC()
	plugin := New()
	plugin.state = &runtimeState{config: &Config{
		TrustDomain: requiredTrustDomain, AgentID: protocol.FixedAgentSPIFFEID,
		SlotOwnerKeySHA256: keyDigest, ChallengeTTL: 30 * time.Second,
		TrusteeTimeout: time.Second, MaxQuoteBytes: protocol.MaxQuoteSize,
	}, verifier: verifier}
	plugin.random = bytes.NewReader(bytes.Repeat([]byte{0x52}, protocol.NonceSize))
	plugin.now = func() time.Time { return currentTime }
	stream := &fakeAttestStream{
		context: context.Background(), helloPayload: helloBytes, privateKey: privateKey,
		quote: []byte{0x01, 0x02, 0x03},
	}
	return plugin, stream, verifier, &currentTime
}

type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }

var _ nodeattestorapi.NodeAttestor_AttestServer = (*fakeAttestStream)(nil)
