package agent

import (
	"fmt"
	"path"
	"time"

	"github.com/hashicorp/hcl"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
)

// Config contains the guest-local paths and limits fixed when SPIRE configures
// the Agent NodeAttestor.
type Config struct {
	EvidenceSocketPath string
	ProofKeyPath       string
	EvidenceTimeout    time.Duration
	MaxQuoteBytes      int64
}

type hclConfig struct {
	EvidenceSocketPath string `hcl:"evidence_socket_path"`
	ProofKeyPath       string `hcl:"proof_key_path"`
	EvidenceTimeout    string `hcl:"evidence_timeout"`
	MaxQuoteBytes      int64  `hcl:"max_quote_bytes"`
}

func parseConfig(_ *configapi.CoreConfiguration, input string) (*Config, []string) {
	raw := hclConfig{
		EvidenceTimeout: "10s",
		MaxQuoteBytes:   protocol.MaxQuoteSize,
	}
	if err := hcl.Decode(&raw, input); err != nil {
		return nil, []string{fmt.Sprintf("decode HCL configuration: %v", err)}
	}

	var notes []string
	if !path.IsAbs(raw.EvidenceSocketPath) {
		notes = append(notes, "evidence_socket_path must be absolute")
	}
	if !path.IsAbs(raw.ProofKeyPath) {
		notes = append(notes, "proof_key_path must be absolute")
	}
	timeout, err := time.ParseDuration(raw.EvidenceTimeout)
	if err != nil || timeout <= 0 {
		notes = append(notes, "evidence_timeout must be greater than zero")
	}
	if raw.MaxQuoteBytes <= 0 || raw.MaxQuoteBytes > protocol.MaxQuoteSize {
		notes = append(notes, fmt.Sprintf("max_quote_bytes must be between 1 and %d", protocol.MaxQuoteSize))
	}
	if len(notes) > 0 {
		return nil, notes
	}
	return &Config{
		EvidenceSocketPath: path.Clean(raw.EvidenceSocketPath),
		ProofKeyPath:       path.Clean(raw.ProofKeyPath),
		EvidenceTimeout:    timeout,
		MaxQuoteBytes:      raw.MaxQuoteBytes,
	}, nil
}
