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
	"errors"
	"fmt"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-workloadattestor/internal/protocol"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// ErrPolicyDenied is emitted only after signature, time, policy and request binding pass.
var ErrPolicyDenied = errors.New("EAR cpu0 appraisal is not affirming")

type tdxEvidence struct {
	CCEventLog    any      `json:"cc_eventlog"`
	Quote         string   `json:"quote"`
	RekorEntryIDs []string `json:"rekor_entry_ids"`
}

type runtimeData struct {
	Structured protocol.RuntimeData `json:"structured"`
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
	Profile   string               `json:"eat_profile"`
	Issuer    string               `json:"iss"`
	IssuedAt  int64                `json:"iat"`
	NotBefore int64                `json:"nbf"`
	Expires   int64                `json:"exp"`
	Submods   map[string]appraisal `json:"submods"`
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
	if endpoint == nil || endpoint.Scheme != "https" || endpoint.Host == "" || endpoint.User != nil || endpoint.RawQuery != "" || endpoint.Fragment != "" {
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
	transport.Proxy = nil
	// TLS authenticates the transport; the separately configured EAR key
	// authenticates the appraisal. Neither key is learned from the response.
	transport.TLSClientConfig = tlsConfig.Clone()
	return &Client{
		httpClient:       &http.Client{Transport: transport, Timeout: timeout, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }},
		attestationURL:   attestationEndpoint.String(),
		earPublicKey:     earPublicKey,
		expectedIssuer:   expectedIssuer,
		expectedProfile:  expectedProfile,
		policyID:         policyID,
		maxResponseBytes: maxResponseBytes,
		now:              time.Now,
	}, nil
}

// Verify accepts only a signed, current Trustee appraisal bound to this request.
func (client *Client) Verify(ctx context.Context, input protocol.Evidence) error {
	canonical, err := input.RuntimeData.Canonical()
	if err != nil {
		return err
	}
	if input.RuntimeData.PolicyID != client.policyID {
		return fmt.Errorf("workload policy mismatch")
	}
	requestBody, err := buildRequest(input, client.policyID)
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, client.attestationURL, bytes.NewReader(requestBody))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/jwt")
	response, err := client.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("call Trustee: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("Trustee returned HTTP %d", response.StatusCode)
	}
	token, err := readLimited(response.Body, client.maxResponseBytes)
	if err != nil {
		return err
	}
	verifiedAt := client.now()
	if err := verifyEAR(token, client.earPublicKey, client.expectedIssuer, client.expectedProfile, client.policyID, canonical, verifiedAt); err != nil {
		return err
	}
	hash := sha256.Sum256(token)
	protocol.LogEvent("workload.ear_accepted", input.RuntimeData.Target, map[string]string{"nonce": input.RuntimeData.Nonce, "ear_sha256": fmt.Sprintf("%x", hash)})
	return nil
}

// Trustee JCS-canonicalizes structured runtime data before SHA-384 hashing.
// TDX pads that 48-byte digest with sixteen zero bytes for REPORTDATA.
func buildRequest(input protocol.Evidence, policyID string) ([]byte, error) {
	if err := protocol.ValidateRekorReferences(input.RekorEntryIDs); err != nil {
		return nil, err
	}
	if _, err := input.RuntimeData.Canonical(); err != nil {
		return nil, err
	}
	quote, err := base64.RawURLEncoding.Strict().DecodeString(input.Quote)
	if err != nil || len(quote) == 0 {
		return nil, fmt.Errorf("invalid TDX Quote")
	}
	inner, err := json.Marshal(tdxEvidence{CCEventLog: nil, Quote: base64.StdEncoding.EncodeToString(quote), RekorEntryIDs: input.RekorEntryIDs})
	if err != nil {
		return nil, err
	}
	return json.Marshal(attestationRequest{
		VerificationRequests: []individualAttestationRequest{{
			TEE: "tdx", Evidence: base64.RawURLEncoding.EncodeToString(inner),
			RuntimeData: runtimeData{Structured: input.RuntimeData}, RuntimeDataHashAlgorithm: "sha384",
		}},
		PolicyIDs: []string{policyID},
	})
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

	// Only authenticated claims may influence admission or policy-denial status.
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
	if claims.NotBefore > nowUnix || claims.IssuedAt <= 0 || claims.IssuedAt > nowUnix || claims.Expires <= nowUnix || claims.Expires <= claims.IssuedAt {
		return fmt.Errorf("EAR validity window is not current")
	}
	cpu, ok := claims.Submods["cpu0"]
	if !ok {
		return fmt.Errorf("EAR cpu0 appraisal missing")
	}
	if cpu.PolicyID != policyID {
		return fmt.Errorf("EAR appraisal policy ID mismatch")
	}
	reportData, err := hex.DecodeString(cpu.AnnotatedEvidence.ReportData)
	if err != nil {
		return fmt.Errorf("decode EAR report_data: %w", err)
	}
	// Bind the signed appraisal to this nonce and every registered target field;
	// a valid EAR for another request or process instance must not be reusable.
	runtimeDigest := sha512.Sum384(runtimeData)
	expectedReportData := append(runtimeDigest[:], make([]byte, 16)...)
	if !bytes.Equal(reportData, expectedReportData) {
		return fmt.Errorf("EAR report_data does not match workload runtime data")
	}
	if cpu.Status == "contraindicated" {
		return ErrPolicyDenied
	}
	if cpu.Status != "affirming" {
		return fmt.Errorf("EAR cpu0 appraisal is indeterminate or unsupported")
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
