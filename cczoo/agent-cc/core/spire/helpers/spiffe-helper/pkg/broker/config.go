// Package broker adds an opt-in, local PID Broker consumer to SPIFFE Helper.
package broker

import (
	"fmt"
	"github.com/hashicorp/hcl/hcl/token"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"net/url"
	"path/filepath"
	"runtime"
	"time"
)

// Config keeps the Helper caller, authenticating Agent, and admitted workload
// identities separate. None is inferred from a business endpoint or API key.
type Config struct {
	WorkloadID             string                 `hcl:"workload_id"`
	Endpoint               string                 `hcl:"endpoint"`
	HelperSPIFFEID         string                 `hcl:"helper_spiffe_id"`
	AgentSPIFFEID          string                 `hcl:"agent_spiffe_id"`
	TargetSPIFFEID         string                 `hcl:"target_spiffe_id"`
	TargetRegistrationPath string                 `hcl:"target_registration_path"`
	PublishHook            string                 `hcl:"publish_hook"`
	StartupTimeout         string                 `hcl:"startup_timeout"`
	UnusedKeyPositions     map[string][]token.Pos `hcl:",unusedKeyPositions"`
}

func (c Config) Validate(certDir string) error {
	if _, err := c.startupTimeout(); err != nil {
		return err
	}
	if runtime.GOOS != "linux" {
		return fmt.Errorf("Broker mode requires Linux pidfd")
	}
	if c.WorkloadID == "" {
		return fmt.Errorf("approved workload_id is required")
	}
	ep, err := url.Parse(c.Endpoint)
	if err != nil || ep.Scheme != "unix" || ep.Host != "" || ep.User != nil || !filepath.IsAbs(ep.Path) || ep.RawQuery != "" || ep.Fragment != "" {
		return fmt.Errorf("broker endpoint must be unix:///absolute/socket")
	}
	for _, p := range []string{certDir, c.TargetRegistrationPath, c.PublishHook} {
		if !filepath.IsAbs(p) {
			return fmt.Errorf("broker paths must be absolute")
		}
	}
	for _, id := range []string{c.HelperSPIFFEID, c.AgentSPIFFEID, c.TargetSPIFFEID} {
		if _, err := spiffeid.FromString(id); err != nil {
			return err
		}
	}
	if c.HelperSPIFFEID == c.TargetSPIFFEID || c.HelperSPIFFEID == c.AgentSPIFFEID || c.TargetSPIFFEID == c.AgentSPIFFEID {
		return fmt.Errorf("Helper, Agent and target identities must be distinct")
	}
	if len(c.UnusedKeyPositions) > 0 {
		return fmt.Errorf("unknown broker configuration")
	}
	return nil
}

func (c Config) startupTimeout() (time.Duration, error) {
	if c.StartupTimeout == "" {
		return 2 * time.Minute, nil
	}
	timeout, err := time.ParseDuration(c.StartupTimeout)
	if err != nil || timeout <= 0 || timeout > 5*time.Minute {
		return 0, fmt.Errorf("startup_timeout must be in (0,5m]")
	}
	return timeout, nil
}
