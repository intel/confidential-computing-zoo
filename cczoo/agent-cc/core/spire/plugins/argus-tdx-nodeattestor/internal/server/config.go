package server

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/hashicorp/hcl"
	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
)

const requiredTrustDomain = "argus.local"

// Config contains the fixed Agent slot, Trustee trust anchors, appraisal pins,
// and protocol limits validated at SPIRE startup.
type Config struct {
	TrustDomain             string
	AgentID                 string
	SlotOwnerKeySHA256      [sha256.Size]byte
	TrusteeURL              *url.URL
	TrusteeTLSConfig        *tls.Config
	EARPublicKey            *ecdsa.PublicKey
	EARExpectedIssuer       string
	EARExpectedProfile      string
	PolicyID                string
	ChallengeTTL            time.Duration
	TrusteeTimeout          time.Duration
	MaxQuoteBytes           int64
	MaxTrusteeResponseBytes int64
}

type hclConfig struct {
	AgentID                 string `hcl:"agent_id"`
	SlotOwnerKeySHA256      string `hcl:"slot_owner_key_sha256"`
	TrusteeURL              string `hcl:"trustee_url"`
	TrusteeCAPath           string `hcl:"trustee_ca_path"`
	TrusteeServerName       string `hcl:"trustee_server_name"`
	EARPublicKeyPath        string `hcl:"ear_public_key_path"`
	EARExpectedIssuer       string `hcl:"ear_expected_issuer"`
	EARExpectedProfile      string `hcl:"ear_expected_profile"`
	PolicyID                string `hcl:"policy_id"`
	ChallengeTTL            string `hcl:"challenge_ttl"`
	TrusteeTimeout          string `hcl:"trustee_timeout"`
	MaxQuoteBytes           int64  `hcl:"max_quote_bytes"`
	MaxTrusteeResponseBytes int64  `hcl:"max_trustee_response_bytes"`
}

func parseConfig(core *configapi.CoreConfiguration, input string) (*Config, []string) {
	raw := hclConfig{
		ChallengeTTL:            "30s",
		TrusteeTimeout:          "15s",
		MaxQuoteBytes:           protocol.MaxQuoteSize,
		MaxTrusteeResponseBytes: 1 << 20,
	}
	if err := hcl.Decode(&raw, input); err != nil {
		return nil, []string{fmt.Sprintf("decode HCL configuration: %v", err)}
	}
	var notes []string
	if core == nil || core.TrustDomain != requiredTrustDomain {
		notes = append(notes, "core trust_domain must be argus.local")
	}
	if raw.AgentID != protocol.FixedAgentSPIFFEID {
		notes = append(notes, "agent_id must be "+protocol.FixedAgentSPIFFEID)
	}
	slotOwnerKeySHA256, err := parseSHA256(raw.SlotOwnerKeySHA256)
	if err != nil {
		notes = append(notes, "slot_owner_key_sha256 must be 64 lowercase hexadecimal characters")
	}
	trusteeURL, err := parseTrusteeURL(raw.TrusteeURL)
	if err != nil {
		notes = append(notes, err.Error())
	}
	tlsConfig, err := loadTLSConfig(raw.TrusteeCAPath, raw.TrusteeServerName)
	if err != nil {
		notes = append(notes, err.Error())
	}
	earPublicKey, err := loadEARPublicKey(raw.EARPublicKeyPath)
	if err != nil {
		notes = append(notes, err.Error())
	}
	if raw.EARExpectedIssuer == "" {
		notes = append(notes, "ear_expected_issuer is required")
	}
	if raw.EARExpectedProfile == "" {
		notes = append(notes, "ear_expected_profile is required")
	}
	if raw.PolicyID == "" || url.PathEscape(raw.PolicyID) != raw.PolicyID {
		notes = append(notes, "policy_id must be one URL path segment")
	}
	challengeTTL, err := time.ParseDuration(raw.ChallengeTTL)
	if err != nil || challengeTTL <= 0 {
		notes = append(notes, "challenge_ttl must be greater than zero")
	}
	trusteeTimeout, err := time.ParseDuration(raw.TrusteeTimeout)
	if err != nil || trusteeTimeout <= 0 {
		notes = append(notes, "trustee_timeout must be greater than zero")
	}
	if raw.MaxQuoteBytes <= 0 || raw.MaxQuoteBytes > protocol.MaxQuoteSize {
		notes = append(notes, fmt.Sprintf("max_quote_bytes must be between 1 and %d", protocol.MaxQuoteSize))
	}
	if raw.MaxTrusteeResponseBytes <= 0 {
		notes = append(notes, "max_trustee_response_bytes must be greater than zero")
	}
	if len(notes) > 0 {
		return nil, notes
	}
	return &Config{
		TrustDomain:             core.TrustDomain,
		AgentID:                 raw.AgentID,
		SlotOwnerKeySHA256:      slotOwnerKeySHA256,
		TrusteeURL:              trusteeURL,
		TrusteeTLSConfig:        tlsConfig,
		EARPublicKey:            earPublicKey,
		EARExpectedIssuer:       raw.EARExpectedIssuer,
		EARExpectedProfile:      raw.EARExpectedProfile,
		PolicyID:                raw.PolicyID,
		ChallengeTTL:            challengeTTL,
		TrusteeTimeout:          trusteeTimeout,
		MaxQuoteBytes:           raw.MaxQuoteBytes,
		MaxTrusteeResponseBytes: raw.MaxTrusteeResponseBytes,
	}, nil
}

func parseTrusteeURL(value string) (*url.URL, error) {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return nil, fmt.Errorf("trustee_url must be an HTTPS origin")
	}
	parsed.Path = ""
	return parsed, nil
}

// loadTLSConfig authenticates the Trustee endpoint with the configured CA and
// server name. This profile does not provision a Trustee client certificate.
func loadTLSConfig(caPath, serverName string) (*tls.Config, error) {
	if serverName == "" || strings.ContainsAny(serverName, "/:@") {
		return nil, fmt.Errorf("trustee_server_name is invalid")
	}
	caPEM, err := readRegularFile(caPath, "trustee_ca_path")
	if err != nil {
		return nil, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("trustee_ca_path contains no certificates")
	}
	return &tls.Config{RootCAs: roots, ServerName: serverName}, nil
}

// loadEARPublicKey pins the independent key used to authenticate Trustee EARs.
func loadEARPublicKey(path string) (*ecdsa.PublicKey, error) {
	contents, err := readRegularFile(path, "ear_public_key_path")
	if err != nil {
		return nil, err
	}
	block, rest := pem.Decode(contents)
	if block == nil || block.Type != "PUBLIC KEY" || len(rest) != 0 {
		return nil, fmt.Errorf("ear_public_key_path must contain one PUBLIC KEY PEM block")
	}
	parsed, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse EAR public key: %w", err)
	}
	publicKey, ok := parsed.(*ecdsa.PublicKey)
	if !ok || publicKey.Curve != elliptic.P256() {
		return nil, fmt.Errorf("EAR public key must use P-256")
	}
	return publicKey, nil
}

func readRegularFile(path, name string) ([]byte, error) {
	if !filepath.IsAbs(path) {
		return nil, fmt.Errorf("%s must be absolute", name)
	}
	info, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("%s must be a regular file", name)
	}
	contents, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", name, err)
	}
	return contents, nil
}

func parseSHA256(value string) ([sha256.Size]byte, error) {
	var digest [sha256.Size]byte
	decoded, err := hex.DecodeString(value)
	if err != nil || len(decoded) != sha256.Size || hex.EncodeToString(decoded) != value {
		return digest, fmt.Errorf("invalid SHA-256")
	}
	copy(digest[:], decoded)
	return digest, nil
}
