package server

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	configapi "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
)

func TestParseConfigLoadsFixedIdentityAndTrusteePins(t *testing.T) {
	paths := writeConfigFixtures(t, t.TempDir())
	config, notes := parseConfig(&configapi.CoreConfiguration{TrustDomain: "argus.local"}, validServerHCL(paths))
	if len(notes) != 0 {
		t.Fatalf("config notes = %v", notes)
	}
	if config.AgentID != protocol.FixedAgentSPIFFEID {
		t.Fatalf("Agent ID = %q", config.AgentID)
	}
	if got := hex.EncodeToString(config.SlotOwnerKeySHA256[:]); got != strings.Repeat("ab", sha256.Size) {
		t.Fatalf("slot owner key digest = %q", got)
	}
	if config.TrusteeURL.String() != "https://trustee.argus.local" {
		t.Fatalf("Trustee URL = %q", config.TrusteeURL)
	}
	if config.TrusteeTLSConfig.ServerName != "trustee.argus.local" || config.EARPublicKey == nil {
		t.Fatal("Trustee TLS or EAR key was not loaded")
	}
	if config.PolicyID != "argus-node-tdx-0123" || config.ChallengeTTL != 30*time.Second {
		t.Fatalf("config = %#v", config)
	}
}

func TestParseConfigRejectsOtherTrustDomainAgentAndNonHTTPSTrustee(t *testing.T) {
	paths := writeConfigFixtures(t, t.TempDir())
	input := strings.Replace(validServerHCL(paths), `trustee_url = "https://trustee.argus.local"`, `trustee_url = "http://trustee.argus.local"`, 1)
	input = strings.Replace(input, protocol.FixedAgentSPIFFEID, "spiffe://argus.local/spire/agent/other", 1)
	config, notes := parseConfig(&configapi.CoreConfiguration{TrustDomain: "other.local"}, input)
	if config != nil || len(notes) < 3 {
		t.Fatalf("config = %#v, notes = %v", config, notes)
	}
}

type fixturePaths struct {
	ca, earKey string
}

func writeConfigFixtures(t *testing.T, directory string) fixturePaths {
	t.Helper()
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "Test CA"},
		NotBefore:             now.Add(-time.Hour),
		NotAfter:              now.Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign,
	}
	certificate, err := x509.CreateCertificate(rand.Reader, template, template, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	earKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	earDER, err := x509.MarshalPKIXPublicKey(&earKey.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	paths := fixturePaths{
		ca:     filepath.ToSlash(filepath.Join(directory, "ca.pem")),
		earKey: filepath.ToSlash(filepath.Join(directory, "ear-public-key.pem")),
	}
	writePEM(t, paths.ca, "CERTIFICATE", certificate)
	writePEM(t, paths.earKey, "PUBLIC KEY", earDER)
	return paths
}

func writePEM(t *testing.T, path, kind string, contents []byte) {
	t.Helper()
	if err := os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: kind, Bytes: contents}), 0o644); err != nil {
		t.Fatal(err)
	}
}

func validServerHCL(paths fixturePaths) string {
	return `
agent_id = "` + protocol.FixedAgentSPIFFEID + `"
slot_owner_key_sha256 = "` + strings.Repeat("ab", sha256.Size) + `"
trustee_url = "https://trustee.argus.local"
trustee_ca_path = "` + paths.ca + `"
trustee_server_name = "trustee.argus.local"
ear_public_key_path = "` + paths.earKey + `"
ear_expected_issuer = "https://trustee.argus.local"
ear_expected_profile = "tag:github.com,2024:confidential-containers/Trustee"
policy_id = "argus-node-tdx-0123"
challenge_ttl = "30s"
trustee_timeout = "15s"
max_quote_bytes = 1048576
max_trustee_response_bytes = 1048576
`
}
