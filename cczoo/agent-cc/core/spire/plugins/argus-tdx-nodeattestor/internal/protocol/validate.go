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
	"fmt"
	"time"

	nodeattestor "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/gen/argus/spire/nodeattestor"
	"google.golang.org/protobuf/proto"
)

// ValidateAgentHello enforces the initial payload accepted by the Server.
func ValidateAgentHello(hello *nodeattestor.AgentHello) error {
	if hello == nil {
		return fmt.Errorf("AgentHello is required")
	}
	if proto.Size(hello) > MaxAgentHelloSize {
		return fmt.Errorf("AgentHello exceeds %d bytes", MaxAgentHelloSize)
	}
	if len(hello.ProtoReflect().GetUnknown()) != 0 {
		return fmt.Errorf("AgentHello contains unknown fields")
	}
	if len(hello.ProofPublicKey) != PublicKeySize {
		return fmt.Errorf("proof public key must be %d bytes", PublicKeySize)
	}
	return nil
}

// ValidateNodeChallenge rejects malformed or already-expired Server challenges.
func ValidateNodeChallenge(challenge *nodeattestor.NodeChallenge) error {
	return validateNodeChallengeAt(challenge, uint64(time.Now().UnixMilli()))
}

func validateNodeChallengeAt(challenge *nodeattestor.NodeChallenge, nowUnixMs uint64) error {
	if challenge == nil {
		return fmt.Errorf("NodeChallenge is required")
	}
	if proto.Size(challenge) > MaxChallengeSize {
		return fmt.Errorf("NodeChallenge exceeds %d bytes", MaxChallengeSize)
	}
	if len(challenge.ProtoReflect().GetUnknown()) != 0 {
		return fmt.Errorf("NodeChallenge contains unknown fields")
	}
	if len(challenge.Nonce) != NonceSize {
		return fmt.Errorf("nonce must be %d bytes", NonceSize)
	}
	if challenge.ExpiresAtUnixMs <= nowUnixMs {
		return fmt.Errorf("NodeChallenge is expired")
	}
	return nil
}

// ValidateNodeEvidenceResponse bounds the Quote and proof before cryptographic
// verification or Trustee I/O.
func ValidateNodeEvidenceResponse(response *nodeattestor.NodeEvidenceResponse, maxQuoteBytes int64) error {
	if response == nil {
		return fmt.Errorf("NodeEvidenceResponse is required")
	}
	if proto.Size(response) > MaxNodeEvidenceResponseSize {
		return fmt.Errorf("NodeEvidenceResponse exceeds %d bytes", MaxNodeEvidenceResponseSize)
	}
	if len(response.ProtoReflect().GetUnknown()) != 0 {
		return fmt.Errorf("NodeEvidenceResponse contains unknown fields")
	}
	if maxQuoteBytes <= 0 || maxQuoteBytes > MaxQuoteSize {
		return fmt.Errorf("maximum TDX Quote size is invalid")
	}
	if len(response.TdxQuote) == 0 || int64(len(response.TdxQuote)) > maxQuoteBytes {
		return fmt.Errorf("TDX Quote size is outside the allowed range")
	}
	if len(response.TranscriptSignature) != SignatureSize {
		return fmt.Errorf("transcript signature must be %d bytes", SignatureSize)
	}
	return nil
}
