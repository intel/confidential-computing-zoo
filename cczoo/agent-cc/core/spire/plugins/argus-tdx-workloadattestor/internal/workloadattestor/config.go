// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package workloadattestor

import (
	"fmt"
	"github.com/hashicorp/hcl"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-workloadattestor/internal/protocol"
	"net/url"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// Config holds operator-approved baselines and Trustee trust settings. A target
// registration supplies observations; it cannot approve its own image or config.
// ConfigEnv declares the application's config-path variable as part of the
// approved baseline; live process checks require that exact environment binding.
type Config struct {
	AgentID                                                                    string
	EvidenceEndpoint, TrusteeEndpoint                                          *url.URL
	TargetRegistrationPath, TrusteeCAPath, TrusteeServerName, EARPublicKeyPath string
	EARExpectedIssuer, EARExpectedProfile, WorkloadID, PolicyID                string
	ImageConfigDigest, ConfigDigest                                            string
	ConfigEnv                                                                  string
	RequestTimeout                                                             time.Duration
	MaxResponseBytes                                                           int64
}
type hclConfig struct {
	AgentID                string   `hcl:"agent_id"`
	EvidenceEndpoint       string   `hcl:"evidence_endpoint"`
	TrusteeEndpoint        string   `hcl:"trustee_endpoint"`
	TargetRegistrationPath string   `hcl:"target_registration_path"`
	TrusteeCAPath          string   `hcl:"trustee_ca_path"`
	TrusteeServerName      string   `hcl:"trustee_server_name"`
	EARPublicKeyPath       string   `hcl:"ear_public_key_path"`
	EARExpectedIssuer      string   `hcl:"ear_expected_issuer"`
	EARExpectedProfile     string   `hcl:"ear_expected_profile"`
	WorkloadID             string   `hcl:"workload_id"`
	PolicyID               string   `hcl:"policy_id"`
	ImageConfigDigest      string   `hcl:"image_config_digest"`
	ConfigDigest           string   `hcl:"config_digest"`
	ConfigEnv              string   `hcl:"config_env"`
	RequestTimeout         string   `hcl:"request_timeout"`
	MaxResponseBytes       int64    `hcl:"max_response_bytes"`
	Unused                 []string `hcl:",unusedKeys"`
}

func parseConfig(input string) (*Config, []string) {
	raw := hclConfig{RequestTimeout: "55s", MaxResponseBytes: 2 << 20}
	if err := hcl.Decode(&raw, input); err != nil {
		return nil, []string{err.Error()}
	}
	var notes []string
	if err := protocol.ValidateAgentID(raw.AgentID); err != nil {
		notes = append(notes, err.Error())
	}
	if len(raw.Unused) > 0 {
		// A misspelled security setting must fail configuration, not be ignored.
		notes = append(notes, "unknown configuration: "+strings.Join(raw.Unused, ", "))
	}
	ep, err := url.Parse(raw.EvidenceEndpoint)
	if err != nil || ep == nil {
		notes = append(notes, "invalid evidence_endpoint")
	} else if err = validateEvidenceEndpoint(ep); err != nil {
		notes = append(notes, err.Error())
	}
	tp, err := url.Parse(raw.TrusteeEndpoint)
	if err != nil || tp.Scheme != "https" || tp.Host == "" || tp.User != nil || (tp.Path != "" && tp.Path != "/") || tp.RawQuery != "" || tp.Fragment != "" {
		notes = append(notes, "trustee_endpoint must be an HTTPS origin")
	}
	for key, value := range map[string]string{"target_registration_path": raw.TargetRegistrationPath, "trustee_ca_path": raw.TrusteeCAPath, "ear_public_key_path": raw.EARPublicKeyPath} {
		if !absoluteForHostOrLinux(value) {
			notes = append(notes, key+" must be absolute")
		}
	}
	if raw.TrusteeServerName == "" || strings.ContainsAny(raw.TrusteeServerName, "/:@ ") {
		notes = append(notes, "trustee_server_name must be a DNS name")
	}
	if raw.EARExpectedIssuer == "" || raw.EARExpectedProfile == "" {
		notes = append(notes, "fixed EAR issuer and profile are required")
	}
	for _, v := range []string{raw.WorkloadID, raw.PolicyID} {
		if !validSelectorComponent(v) {
			notes = append(notes, "workload_id and policy_id must be nonempty selector components")
		}
	}
	for _, v := range []string{raw.ImageConfigDigest, raw.ConfigDigest} {
		if !regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(v) {
			notes = append(notes, "approved image_config_digest and config_digest must be sha256 digests")
		}
	}
	if !regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]{0,127}$`).MatchString(raw.ConfigEnv) {
		notes = append(notes, "config_env must name the approved configuration environment variable")
	}
	timeout, err := time.ParseDuration(raw.RequestTimeout)
	if err != nil || timeout <= 50*time.Second || timeout > 60*time.Second {
		notes = append(notes, "request_timeout must be in (50s,60s], above the Trustee verifier budget")
	}
	if raw.MaxResponseBytes <= 0 || raw.MaxResponseBytes > 4<<20 {
		notes = append(notes, "max_response_bytes must be in (0,4194304]")
	}
	if len(notes) > 0 {
		return nil, notes
	}
	return &Config{raw.AgentID, ep, tp, raw.TargetRegistrationPath, raw.TrusteeCAPath, raw.TrusteeServerName, raw.EARPublicKeyPath, raw.EARExpectedIssuer, raw.EARExpectedProfile, raw.WorkloadID, raw.PolicyID, raw.ImageConfigDigest, raw.ConfigDigest, raw.ConfigEnv, timeout, raw.MaxResponseBytes}, nil
}
func validateEvidenceEndpoint(ep *url.URL) error {
	if ep.Scheme != "unix" || ep.Host != "" || ep.User != nil || !path.IsAbs(ep.Path) || ep.RawQuery != "" || ep.Fragment != "" {
		return fmt.Errorf("evidence_endpoint must be unix:///absolute/socket")
	}
	return nil
}
func absoluteForHostOrLinux(v string) bool { return filepath.IsAbs(v) || path.IsAbs(v) }
func validSelectorComponent(v string) bool {
	return regexp.MustCompile(`^[A-Za-z0-9_.-]{1,128}$`).MatchString(v)
}

// checkApproved compares observations with the independent configured baseline
// before any Quote is requested or selectors are returned.
func (c *Config) checkApproved(t protocol.Target) error {
	if err := t.Validate(); err != nil {
		return err
	}
	if t.AgentID != c.AgentID || t.WorkloadID != c.WorkloadID || t.PolicyID != c.PolicyID || t.ImageConfigDigest != c.ImageConfigDigest || t.ConfigDigest != c.ConfigDigest || t.ConfigEnv != c.ConfigEnv {
		return fmt.Errorf("target differs from approved workload baseline")
	}
	return nil
}
