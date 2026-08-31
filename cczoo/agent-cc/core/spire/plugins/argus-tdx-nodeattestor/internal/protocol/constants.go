// Package protocol defines the private Agent/Server messages and cryptographic
// bindings used by the Argus TDX NodeAttestor.
package protocol

const (
	// FixedAgentSPIFFEID is the only Agent identity admitted by this profile.
	// The Rust Evidence Provider binds the same value into TDX REPORTDATA.
	FixedAgentSPIFFEID = "spiffe://argus.local/spire/agent/argus_tdx/openviking-node"

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
