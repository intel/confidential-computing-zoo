// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
