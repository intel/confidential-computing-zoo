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

// Package protocol defines the private Agent/Server messages and cryptographic
// bindings used by the Argus TDX NodeAttestor.
package protocol

const (
	// Cryptographic field sizes are fixed by Ed25519 and the Node protocol.
	PublicKeySize = 32
	NonceSize     = 32
	SignatureSize = 64

	// Message limits bound every payload before protobuf or Quote processing.
	// MaxQuoteSize matches the Rust Provider's bounded TSM Quote read.
	MaxAgentHelloSize           = 4 << 10
	MaxChallengeSize            = 4 << 10
	MaxQuoteSize                = 4 << 20
	MaxNodeEvidenceResponseSize = MaxQuoteSize + 4<<10

	// reportDataDomain must match NODE_BINDING_DOMAIN in the Rust Provider.
	reportDataDomain = "argus.node.tdx.reportdata"
	transcriptDomain = "argus.node.tdx.transcript"
)
