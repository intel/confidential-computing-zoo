package agent

import (
	"context"
	"testing"
	"time"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
)

const validAgentConfig = `
evidence_socket_path = "/run/argus/evidence-provider.sock"
proof_key_path = "/var/lib/spire/argus-tdx/proof-key.pem"
`

func TestParseConfigAcceptsNodeEvidenceSettings(t *testing.T) {
	config, notes := parseConfig(nil, validAgentConfig)
	if len(notes) != 0 {
		t.Fatalf("valid config notes = %v", notes)
	}
	if config.EvidenceSocketPath != "/run/argus/evidence-provider.sock" {
		t.Fatalf("evidence socket = %q", config.EvidenceSocketPath)
	}
	if config.ProofKeyPath != "/var/lib/spire/argus-tdx/proof-key.pem" {
		t.Fatalf("proof key path = %q", config.ProofKeyPath)
	}
	if config.EvidenceTimeout != 10*time.Second {
		t.Fatalf("evidence timeout = %s", config.EvidenceTimeout)
	}
	if config.MaxQuoteBytes != protocol.MaxQuoteSize {
		t.Fatalf("maximum Quote bytes = %d", config.MaxQuoteBytes)
	}
}

func TestParseConfigRejectsInvalidPathsAndLimits(t *testing.T) {
	config, notes := parseConfig(nil, `
evidence_socket_path = "evidence.sock"
proof_key_path = "proof-key.pem"
evidence_timeout = "0s"
max_quote_bytes = 4194305
`)
	if config != nil || len(notes) != 4 {
		t.Fatalf("config = %#v, notes = %v", config, notes)
	}
}

func TestValidateDoesNotChangeConfiguredSnapshot(t *testing.T) {
	plugin := New()
	if _, err := plugin.Configure(context.Background(), &configapi.ConfigureRequest{HclConfiguration: validAgentConfig}); err != nil {
		t.Fatal(err)
	}
	before, err := plugin.getConfig()
	if err != nil {
		t.Fatal(err)
	}
	response, err := plugin.Validate(context.Background(), &configapi.ValidateRequest{HclConfiguration: `evidence_socket_path = "relative.sock"`})
	if err != nil {
		t.Fatal(err)
	}
	if response.Valid {
		t.Fatal("invalid config was reported valid")
	}
	after, err := plugin.getConfig()
	if err != nil {
		t.Fatal(err)
	}
	if before != after {
		t.Fatal("Validate changed the active config snapshot")
	}
}
