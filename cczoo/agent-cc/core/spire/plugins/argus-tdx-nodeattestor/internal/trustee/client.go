// Package trustee submits raw TDX evidence for appraisal and verifies the
// signed EAR returned by Trustee. It does not parse or appraise Quotes locally.
package trustee

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/sha256"
	"crypto/sha512"
	"crypto/tls"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// VerifyInput couples a raw Quote with the canonical runtime bytes from which
// this protocol derives the expected REPORTDATA.
type VerifyInput struct {
	Quote       []byte
	RuntimeData []byte
}

// VerifiedNodeClaims intentionally carries no selectors. The Trustee decision
// gates the one fixed Agent identity configured by this NodeAttestor.
type VerifiedNodeClaims struct{}

type tdxEvidence struct {
	CCEventLog any    `json:"cc_eventlog"`
	Quote      string `json:"quote"`
}

type runtimeData struct {
	Raw string `json:"raw"`
}

type individualAttestationRequest struct {
	TEE                      string      `json:"tee"`
	Evidence                 string      `json:"evidence"`
	RuntimeData              runtimeData `json:"runtime_data"`
	RuntimeDataHashAlgorithm string      `json:"runtime_data_hash_algorithm"`
}

type attestationRequest struct {
	VerificationRequests []individualAttestationRequest `json:"verification_requests"`
	PolicyIDs            []string                       `json:"policy_ids"`
}

type earHeader struct {
	Algorithm string `json:"alg"`
}

type annotatedEvidence struct {
	ReportData string `json:"report_data"`
}

type appraisal struct {
	Status            string            `json:"ear.status"`
	PolicyID          string            `json:"ear.appraisal-policy-id"`
	AnnotatedEvidence annotatedEvidence `json:"ear.veraison.annotated-evidence"`
}

type earClaims struct {
	Profile  string               `json:"eat_profile"`
	Issuer   string               `json:"iss"`
	IssuedAt int64                `json:"iat"`
	Expires  int64                `json:"exp"`
	Submods  map[string]appraisal `json:"submods"`
}

// Client calls one pinned Trustee origin and verifies EARs against fixed
// issuer, profile, policy, and signing-key expectations.
type Client struct {
	httpClient       *http.Client
	attestationURL   string
	earPublicKey     *ecdsa.PublicKey
	expectedIssuer   string
	expectedProfile  string
	policyID         string
	maxResponseBytes int64
	now              func() time.Time
}

// NewClient constructs a bounded Trustee appraisal client.
func NewClient(
	endpoint *url.URL,
	tlsConfig *tls.Config,
	earPublicKey *ecdsa.PublicKey,
	expectedIssuer string,
	expectedProfile string,
	policyID string,
	timeout time.Duration,
	maxResponseBytes int64,
) (*Client, error) {
	if endpoint == nil || endpoint.Scheme != "https" || endpoint.Host == "" || endpoint.RawQuery != "" || endpoint.Fragment != "" {
		return nil, fmt.Errorf("Trustee endpoint must be an HTTPS origin")
	}
	if endpoint.Path != "" && endpoint.Path != "/" {
		return nil, fmt.Errorf("Trustee endpoint must not contain a path")
	}
	if tlsConfig == nil || tlsConfig.RootCAs == nil {
		return nil, fmt.Errorf("Trustee TLS configuration is incomplete")
	}
	if earPublicKey == nil || earPublicKey.Curve != elliptic.P256() {
		return nil, fmt.Errorf("EAR public key must use P-256")
	}
	if expectedIssuer == "" || expectedProfile == "" || policyID == "" || url.PathEscape(policyID) != policyID {
		return nil, fmt.Errorf("Trustee EAR configuration is invalid")
	}
	if timeout <= 0 || maxResponseBytes <= 0 {
		return nil, fmt.Errorf("Trustee client limits are invalid")
	}

	attestationEndpoint := *endpoint
	attestationEndpoint.Path = "/attestation"
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSClientConfig = tlsConfig.Clone()
	return &Client{
		httpClient:       &http.Client{Transport: transport, Timeout: timeout},
		attestationURL:   attestationEndpoint.String(),
		earPublicKey:     earPublicKey,
		expectedIssuer:   expectedIssuer,
		expectedProfile:  expectedProfile,
		policyID:         policyID,
		maxResponseBytes: maxResponseBytes,
		now:              time.Now,
	}, nil
}

// VerifyNode accepts a Node only when Trustee returns a current, signed,
// affirming appraisal for the requested policy and REPORTDATA binding.
func (client *Client) VerifyNode(ctx context.Context, input VerifyInput) (VerifiedNodeClaims, error) {
	if len(input.Quote) == 0 {
		return VerifiedNodeClaims{}, fmt.Errorf("TDX Quote is required")
	}
	if len(input.RuntimeData) == 0 {
		return VerifiedNodeClaims{}, fmt.Errorf("node runtime data is required")
	}
	requestBody, err := buildRequest(input, client.policyID)
	if err != nil {
		return VerifiedNodeClaims{}, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, client.attestationURL, bytes.NewReader(requestBody))
	if err != nil {
		return VerifiedNodeClaims{}, fmt.Errorf("create Trustee attestation request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/jwt")
	response, err := client.httpClient.Do(request)
	if err != nil {
		return VerifiedNodeClaims{}, fmt.Errorf("call Trustee attestation endpoint: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return VerifiedNodeClaims{}, fmt.Errorf("Trustee attestation endpoint returned HTTP %d", response.StatusCode)
	}
	token, err := readLimited(response.Body, client.maxResponseBytes)
	if err != nil {
		return VerifiedNodeClaims{}, fmt.Errorf("read Trustee EAR: %w", err)
	}
	if err := verifyEAR(token, client.earPublicKey, client.expectedIssuer, client.expectedProfile, client.policyID, input.RuntimeData, client.now()); err != nil {
		return VerifiedNodeClaims{}, err
	}
	return VerifiedNodeClaims{}, nil
}

// buildRequest follows Trustee v0.21's raw runtime-data contract by sending the
// derived 64-byte REPORTDATA value instead of unhashed NodeRuntimeData.
func buildRequest(input VerifyInput, policyID string) ([]byte, error) {
	inner, err := json.Marshal(tdxEvidence{
		CCEventLog: nil,
		Quote:      base64.StdEncoding.EncodeToString(input.Quote),
	})
	if err != nil {
		return nil, fmt.Errorf("marshal TDX evidence: %w", err)
	}
	// Trustee v0.21 compares raw runtime data directly with TDX REPORTDATA.
	runtimeDigest := sha512.Sum384(input.RuntimeData)
	var reportData [64]byte
	copy(reportData[:], runtimeDigest[:])
	request := attestationRequest{
		VerificationRequests: []individualAttestationRequest{{
			TEE:                      "tdx",
			Evidence:                 base64.RawURLEncoding.EncodeToString(inner),
			RuntimeData:              runtimeData{Raw: base64.RawURLEncoding.EncodeToString(reportData[:])},
			RuntimeDataHashAlgorithm: "sha384",
		}},
		PolicyIDs: []string{policyID},
	}
	encoded, err := json.Marshal(request)
	if err != nil {
		return nil, fmt.Errorf("marshal Trustee request: %w", err)
	}
	return encoded, nil
}

// verifyEAR authenticates the compact JWT before accepting its appraisal and
// annotated evidence as the result of Quote verification.
func verifyEAR(token []byte, publicKey *ecdsa.PublicKey, expectedIssuer, expectedProfile, policyID string, runtimeData []byte, now time.Time) error {
	parts := strings.Split(string(token), ".")
	if len(parts) != 3 {
		return fmt.Errorf("Trustee response is not a compact JWT")
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return fmt.Errorf("decode EAR header: %w", err)
	}
	var header earHeader
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return fmt.Errorf("decode EAR header: %w", err)
	}
	if header.Algorithm != "ES256" {
		return fmt.Errorf("EAR algorithm must be ES256")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(signature) != 64 {
		return fmt.Errorf("decode EAR signature")
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	r := new(big.Int).SetBytes(signature[:32])
	s := new(big.Int).SetBytes(signature[32:])
	if !ecdsa.Verify(publicKey, digest[:], r, s) {
		return fmt.Errorf("EAR signature verification failed")
	}

	claimsBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return fmt.Errorf("decode EAR claims: %w", err)
	}
	var claims earClaims
	if err := json.Unmarshal(claimsBytes, &claims); err != nil {
		return fmt.Errorf("decode EAR claims: %w", err)
	}
	if claims.Issuer != expectedIssuer || claims.Profile != expectedProfile {
		return fmt.Errorf("EAR issuer or profile mismatch")
	}
	nowUnix := now.Unix()
	if claims.IssuedAt <= 0 || claims.IssuedAt > nowUnix || claims.Expires <= nowUnix || claims.Expires <= claims.IssuedAt {
		return fmt.Errorf("EAR validity window is not current")
	}
	cpu, ok := claims.Submods["cpu0"]
	if !ok || cpu.Status != "affirming" {
		return fmt.Errorf("EAR cpu0 appraisal is not affirming")
	}
	if cpu.PolicyID != policyID {
		return fmt.Errorf("EAR appraisal policy ID mismatch")
	}
	reportData, err := hex.DecodeString(cpu.AnnotatedEvidence.ReportData)
	if err != nil {
		return fmt.Errorf("decode EAR report_data: %w", err)
	}
	runtimeDigest := sha512.Sum384(runtimeData)
	expectedReportData := append(runtimeDigest[:], make([]byte, 16)...)
	if !bytes.Equal(reportData, expectedReportData) {
		return fmt.Errorf("EAR report_data does not match node runtime data")
	}
	return nil
}

func readLimited(reader io.Reader, maximum int64) ([]byte, error) {
	contents, err := io.ReadAll(io.LimitReader(reader, maximum+1))
	if err != nil {
		return nil, err
	}
	if int64(len(contents)) > maximum {
		return nil, fmt.Errorf("response exceeds %d bytes", maximum)
	}
	return contents, nil
}
