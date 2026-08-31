package protocol

import (
	"strings"
	"testing"

	nodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
)

func TestValidateNodeMessages(t *testing.T) {
	const now = uint64(1_700_000_000_000)

	tests := []struct {
		name     string
		validate func() error
	}{
		{name: "hello", validate: func() error {
			return ValidateAgentHello(&nodeattestor.AgentHello{ProofPublicKey: make([]byte, PublicKeySize)})
		}},
		{name: "challenge", validate: func() error {
			return validateNodeChallengeAt(&nodeattestor.NodeChallenge{Nonce: make([]byte, NonceSize), ExpiresAtUnixMs: now + 1}, now)
		}},
		{name: "response", validate: func() error {
			return ValidateNodeEvidenceResponse(&nodeattestor.NodeEvidenceResponse{TdxQuote: []byte{1}, TranscriptSignature: make([]byte, SignatureSize)}, 1)
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if err := test.validate(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestValidateNodeMessagesRejectInvalidFields(t *testing.T) {
	const now = uint64(1_700_000_000_000)

	tests := []struct {
		name     string
		validate func() error
		contains string
	}{
		{name: "hello key", contains: "proof public key", validate: func() error {
			return ValidateAgentHello(&nodeattestor.AgentHello{ProofPublicKey: make([]byte, PublicKeySize-1)})
		}},
		{name: "challenge nonce", contains: "nonce", validate: func() error {
			return validateNodeChallengeAt(&nodeattestor.NodeChallenge{Nonce: make([]byte, NonceSize-1), ExpiresAtUnixMs: now + 1}, now)
		}},
		{name: "challenge expired", contains: "expired", validate: func() error {
			return validateNodeChallengeAt(&nodeattestor.NodeChallenge{Nonce: make([]byte, NonceSize), ExpiresAtUnixMs: now}, now)
		}},
		{name: "empty quote", contains: "TDX Quote", validate: func() error {
			return ValidateNodeEvidenceResponse(&nodeattestor.NodeEvidenceResponse{TranscriptSignature: make([]byte, SignatureSize)}, 16)
		}},
		{name: "oversize quote", contains: "TDX Quote", validate: func() error {
			return ValidateNodeEvidenceResponse(&nodeattestor.NodeEvidenceResponse{TdxQuote: make([]byte, 17), TranscriptSignature: make([]byte, SignatureSize)}, 16)
		}},
		{name: "signature", contains: "transcript signature", validate: func() error {
			return ValidateNodeEvidenceResponse(&nodeattestor.NodeEvidenceResponse{TdxQuote: []byte{1}, TranscriptSignature: make([]byte, SignatureSize-1)}, 16)
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := test.validate()
			if err == nil || !strings.Contains(err.Error(), test.contains) {
				t.Fatalf("error = %v, want containing %q", err, test.contains)
			}
		})
	}
}

func TestValidateNodeMessagesRejectUnknownFields(t *testing.T) {
	hello := &nodeattestor.AgentHello{ProofPublicKey: make([]byte, PublicKeySize)}
	hello.ProtoReflect().SetUnknown([]byte{0x98, 0x06, 0x01})
	challenge := &nodeattestor.NodeChallenge{Nonce: make([]byte, NonceSize), ExpiresAtUnixMs: uint64(1 << 63)}
	challenge.ProtoReflect().SetUnknown([]byte{0x98, 0x06, 0x01})
	response := &nodeattestor.NodeEvidenceResponse{TdxQuote: []byte{1}, TranscriptSignature: make([]byte, SignatureSize)}
	response.ProtoReflect().SetUnknown([]byte{0x98, 0x06, 0x01})

	for name, validate := range map[string]func() error{
		"hello":     func() error { return ValidateAgentHello(hello) },
		"challenge": func() error { return ValidateNodeChallenge(challenge) },
		"response":  func() error { return ValidateNodeEvidenceResponse(response, 1) },
	} {
		t.Run(name, func(t *testing.T) {
			if err := validate(); err == nil || !strings.Contains(err.Error(), "unknown") {
				t.Fatalf("unknown field error = %v", err)
			}
		})
	}
}
