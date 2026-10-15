package config

import (
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"slices"
	"strings"

	"github.com/hashicorp/hcl"
	"github.com/hashicorp/hcl/hcl/token"
	"github.com/sirupsen/logrus"
	"github.com/spiffe/spiffe-helper/pkg/broker"
	"github.com/spiffe/spiffe-helper/pkg/health"
	"github.com/spiffe/spiffe-helper/pkg/sidecar"
)

const (
	defaultAgentAddress      = "/tmp/spire-agent/public/api.sock"
	defaultCertFileMode      = 0644
	defaultKeyFileMode       = 0600
	defaultJWTBundleFileMode = 0600
	defaultJWTSVIDFileMode   = 0600
	defaultBindPort          = 8081
	defaultLivenessPath      = "/live"
	defaultReadinessPath     = "/ready"
)

type Config struct {
	Broker                   *broker.Config `hcl:"broker"`
	AddIntermediatesToBundle bool           `hcl:"add_intermediates_to_bundle"`
	AgentAddress             string         `hcl:"agent_address"`
	Cmd                      string         `hcl:"cmd"`
	CmdArgs                  string         `hcl:"cmd_args"`
	PIDFilename              string         `hcl:"pid_file_name"`
	CertDir                  string         `hcl:"cert_dir"`
	CertFileMode             int            `hcl:"cert_file_mode"`
	KeyFileMode              int            `hcl:"key_file_mode"`
	JWTBundleFileMode        int            `hcl:"jwt_bundle_file_mode"`
	JWTSVIDFileMode          int            `hcl:"jwt_svid_file_mode"`
	IncludeFederatedDomains  bool           `hcl:"include_federated_domains"`
	OmitExpired              bool           `hcl:"omit_expired"`
	RenewSignal              string         `hcl:"renew_signal"`
	DaemonMode               *bool          `hcl:"daemon_mode"`
	HealthCheck              health.Config  `hcl:"health_checks"`
	Hint                     string         `hcl:"hint"`

	// x509 configuration
	SVIDFilename       string `hcl:"svid_file_name"`
	SVIDKeyFilename    string `hcl:"svid_key_file_name"`
	SVIDBundleFilename string `hcl:"svid_bundle_file_name"`

	// JWT configuration
	JWTSVIDs          []JWTConfig `hcl:"jwt_svids"`
	JWTBundleFilename string      `hcl:"jwt_bundle_file_name"`

	UnusedKeyPositions map[string][]token.Pos `hcl:",unusedKeyPositions"`
}

type JWTConfig struct {
	JWTAudience       string   `hcl:"jwt_audience"`
	JWTExtraAudiences []string `hcl:"jwt_extra_audiences"`
	JWTSVIDFilename   string   `hcl:"jwt_svid_file_name"`

	UnusedKeyPositions map[string][]token.Pos `hcl:",unusedKeyPositions"`
}

// ParseConfigFile parses the given HCL file into a Config struct
func ParseConfigFile(file string) (*Config, error) {
	// Read HCL file
	dat, err := os.ReadFile(file)
	if err != nil {
		return nil, err
	}

	// Parse HCL
	config := new(Config)
	if err := hcl.Decode(config, string(dat)); err != nil {
		return nil, err
	}

	return config, nil
}

// ParseConfigFlagOverrides handles command line arguments that override config file settings
func (c *Config) ParseConfigFlagOverrides(daemonModeFlag bool, daemonModeFlagName string) {
	if isFlagPassed(daemonModeFlagName) {
		// If daemon mode is set by CLI this takes precedence
		c.DaemonMode = &daemonModeFlag
	} else if c.DaemonMode == nil {
		// If daemon mode is not set, then default to true
		daemonMode := true
		c.DaemonMode = &daemonMode
	}
}

func (c *Config) ValidateConfig(log logrus.FieldLogger) error {
	if err := c.checkForUnknownConfig(); err != nil {
		return err
	}

	if err := validateOSConfig(c); err != nil {
		return err
	}

	for _, jwtConfig := range c.JWTSVIDs {
		if jwtConfig.JWTSVIDFilename == "" {
			return errors.New("'jwt_file_name' is required in 'jwt_svids'")
		}
		if jwtConfig.JWTAudience == "" {
			return errors.New("'jwt_audience' is required in 'jwt_svids'")
		}
	}

	if c.AgentAddress == "" {
		spireAgentAddress := os.Getenv("SPIRE_AGENT_ADDRESS")
		spiffeEndpointSocket := os.Getenv("SPIFFE_ENDPOINT_SOCKET")

		switch {
		case spireAgentAddress != "" && spiffeEndpointSocket == "":
			log.Warn("SPIRE_AGENT_ADDRESS is deprecated and will be removed in 0.10.0. Use SPIFFE_ENDPOINT_SOCKET instead.")
			c.AgentAddress = spireAgentAddress
		case spireAgentAddress != "" && spiffeEndpointSocket != "":
			return errors.New("both SPIRE_AGENT_ADDRESS and SPIFFE_ENDPOINT_SOCKET set. Use SPIFFE_ENDPOINT_SOCKET only. Support for SPIRE_AGENT_ADDRESS is deprecated and will be removed in 0.10.0")
		case spireAgentAddress == "" && spiffeEndpointSocket != "":
			c.AgentAddress = spiffeEndpointSocket
		default:
			c.AgentAddress = defaultAgentAddress
		}
	}

	if c.DaemonMode != nil && !*c.DaemonMode {
		if c.Cmd != "" {
			log.Warn("cmd is set but daemon_mode is false. cmd will be ignored. This may become an error in a future release.")
		}
		if c.RenewSignal != "" {
			log.Warn("renew_signal is set but daemon_mode is false. renew_signal will be ignored. This may become an error in a future release.")
		}
		// pid_file_name is new enough that there should not be existing configurations that use it without daemon_mode
		// so we can error here without backcompat worries. In future we may support one-shot signalling of a process, but
		// it's ignored at the moment so we shouldn't allow the user to think it's doing something.
		if c.PIDFilename != "" {
			return errors.New("pid_file_name is set but daemon_mode is false. pid_file_name is only supported in daemon_mode")
		}
	}

	if c.PIDFilename != "" && c.RenewSignal == "" {
		return errors.New("must specify renew_signal when using pid_file_name")
	}

	if c.Broker != nil {
		// Mixing upstream file writers, command hooks or health endpoints with
		// Broker publication would create two owners of credentials/readiness.
		if c.DaemonMode == nil || !*c.DaemonMode || len(c.JWTSVIDs) > 0 || c.JWTBundleFilename != "" || c.Cmd != "" || c.PIDFilename != "" || c.RenewSignal != "" || c.HealthCheck.ListenerEnabled || c.SVIDFilename != "" || c.SVIDKeyFilename != "" || c.SVIDBundleFilename != "" {
			return errors.New("Broker mode supports daemon X.509 only; lifecycle uses publish_hook and readiness file")
		}
		return c.Broker.Validate(c.CertDir)
	}
	x509Enabled, err := validateX509Config(c)
	if err != nil {
		return err
	}

	jwtBundleEnabled, jwtSVIDsEnabled := validateJWTConfig(c)

	if !x509Enabled && !jwtBundleEnabled && !jwtSVIDsEnabled {
		return errors.New("at least one of the sets ('svid_file_name', 'svid_key_file_name', 'svid_bundle_file_name'), 'jwt_svids', or 'jwt_bundle_file_name' must be fully specified")
	}

	if c.CertFileMode < 0 {
		return errors.New("cert file mode must be positive")
	} else if c.CertFileMode == 0 {
		c.CertFileMode = defaultCertFileMode
	}
	if c.KeyFileMode < 0 {
		return errors.New("key file mode must be positive")
	} else if c.KeyFileMode == 0 {
		c.KeyFileMode = defaultKeyFileMode
	}
	if c.JWTBundleFileMode < 0 {
		return errors.New("jwt bundle file mode must be positive")
	} else if c.JWTBundleFileMode == 0 {
		c.JWTBundleFileMode = defaultJWTBundleFileMode
	}
	if c.JWTSVIDFileMode < 0 {
		return errors.New("jwt svid file mode must be positive")
	} else if c.JWTSVIDFileMode == 0 {
		c.JWTSVIDFileMode = defaultJWTSVIDFileMode
	}

	if c.HealthCheck.ListenerEnabled {
		if c.HealthCheck.BindPort < 0 {
			return errors.New("bind port must be positive")
		}
		if c.HealthCheck.BindPort == 0 {
			c.HealthCheck.BindPort = defaultBindPort
		}
		if c.HealthCheck.LivenessPath == "" {
			c.HealthCheck.LivenessPath = defaultLivenessPath
		}
		if c.HealthCheck.ReadinessPath == "" {
			c.HealthCheck.ReadinessPath = defaultReadinessPath
		}
	}

	return nil
}

// checkForUnknownConfig looks for any unknown configuration keys and returns an error if one is found
func (c *Config) checkForUnknownConfig() error {
	if len(c.UnusedKeyPositions) != 0 {
		return fmt.Errorf("unknown top level key(s): %s", mapKeysToString(c.UnusedKeyPositions))
	}

	for i, jwtSVID := range c.JWTSVIDs {
		if len(jwtSVID.UnusedKeyPositions) != 0 {
			return fmt.Errorf("unknown key(s) in jwt_svids[%d]: %s", i, mapKeysToString(jwtSVID.UnusedKeyPositions))
		}
	}

	return nil
}

func ParseConfig(configFile string, daemonModeFlag bool, daemonModeFlagName string) (*Config, error) {
	hclConfig, err := ParseConfigFile(configFile)
	if err != nil {
		return nil, fmt.Errorf("failed to parse %q: %w", configFile, err)
	}
	hclConfig.ParseConfigFlagOverrides(daemonModeFlag, daemonModeFlagName)
	return hclConfig, nil
}

func NewSidecarConfig(config *Config, log logrus.FieldLogger) *sidecar.Config {
	sidecarConfig := &sidecar.Config{
		AddIntermediatesToBundle: config.AddIntermediatesToBundle,
		AgentAddress:             config.AgentAddress,
		Cmd:                      config.Cmd,
		CmdArgs:                  config.CmdArgs,
		PIDFilename:              config.PIDFilename,
		CertDir:                  config.CertDir,
		CertFileMode:             fs.FileMode(config.CertFileMode),      //nolint:gosec
		KeyFileMode:              fs.FileMode(config.KeyFileMode),       //nolint:gosec
		JWTBundleFileMode:        fs.FileMode(config.JWTBundleFileMode), //nolint:gosec
		JWTSVIDFileMode:          fs.FileMode(config.JWTSVIDFileMode),   //nolint:gosec
		IncludeFederatedDomains:  config.IncludeFederatedDomains,
		OmitExpired:              config.OmitExpired,
		JWTBundleFilename:        config.JWTBundleFilename,
		Log:                      log,
		RenewSignal:              config.RenewSignal,
		SVIDFilename:             config.SVIDFilename,
		SVIDKeyFilename:          config.SVIDKeyFilename,
		SVIDBundleFilename:       config.SVIDBundleFilename,
		Hint:                     config.Hint,
	}

	for _, jwtSVID := range config.JWTSVIDs {
		sidecarConfig.JWTSVIDs = append(sidecarConfig.JWTSVIDs, sidecar.JWTConfig{
			JWTAudience:       jwtSVID.JWTAudience,
			JWTExtraAudiences: jwtSVID.JWTExtraAudiences,
			JWTSVIDFilename:   jwtSVID.JWTSVIDFilename,
		})
	}

	return sidecarConfig
}

func validateX509Config(c *Config) (bool, error) {
	x509EmptyCount := countEmpty(c.SVIDFilename, c.SVIDBundleFilename, c.SVIDKeyFilename)
	if x509EmptyCount != 0 && x509EmptyCount != 3 {
		return false, errors.New("all or none of 'svid_file_name', 'svid_key_file_name', 'svid_bundle_file_name' must be specified")
	}

	return x509EmptyCount == 0, nil
}

func validateJWTConfig(c *Config) (bool, bool) {
	jwtBundleEmptyCount := countEmpty(c.JWTBundleFilename)

	return jwtBundleEmptyCount == 0, len(c.JWTSVIDs) > 0
}

func countEmpty(configs ...string) int {
	cnt := 0
	for _, config := range configs {
		if config == "" {
			cnt++
		}
	}

	return cnt
}

// isFlagPassed tests to see if a command line argument was set at all or left empty
func isFlagPassed(name string) bool {
	var found bool
	flag.Visit(func(f *flag.Flag) {
		if f.Name == name {
			found = true
		}
	})

	return found
}

// mapKeysToString returns a comma separated string with all the keys from a map
func mapKeysToString[V any](myMap map[string]V) string {
	keys := make([]string, 0, len(myMap))
	for key := range myMap {
		keys = append(keys, key)
	}

	slices.Sort(keys)
	return strings.Join(keys, ",")
}
