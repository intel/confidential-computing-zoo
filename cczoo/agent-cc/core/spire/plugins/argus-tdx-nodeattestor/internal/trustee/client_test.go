package trustee

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const (
	testPolicyID = "argus-node-tdx-0123"
	testIssuer   = "https://trustee.argus.local"
	testProfile  = "tag:github.com,2024:confidential-containers/Trustee"
)

func TestVerifyNodeSendsReportDataAndAcceptsAffirmingEAR(t *testing.T) {
	now := time.Date(2026, 8, 27, 1, 2, 3, 0, time.UTC)
	quote := []byte{0x01, 0x02, 0x03, 0x04}
	runtimeData := []byte("node-runtime-data")
	key := newSigningKey(t)

	var paths []string
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		paths = append(paths, request.Method+" "+request.URL.Path)
		switch request.URL.Path {
		case "/attestation":
			contents, err := io.ReadAll(request.Body)
			if err != nil {
				t.Error(err)
				return
			}
			assertTrusteeRequest(t, contents, quote, runtimeData)
			_, _ = writer.Write([]byte(signEAR(t, key, validClaims(now, runtimeData))))
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()

	client := testClient(server, key, now)
	if _, err := client.VerifyNode(context.Background(), VerifyInput{Quote: quote, RuntimeData: runtimeData}); err != nil {
		t.Fatal(err)
	}
	if got, want := strings.Join(paths, ","), "POST /attestation"; got != want {
		t.Fatalf("requests = %q, want %q", got, want)
	}
}

func TestVerifyNodeRejectsInvalidEAR(t *testing.T) {
	now := time.Date(2026, 8, 27, 1, 2, 3, 0, time.UTC)
	runtimeData := []byte("node-runtime-data")
	key := newSigningKey(t)
	otherKey := newSigningKey(t)

	tests := map[string]func(map[string]any) (*ecdsa.PrivateKey, map[string]any){
		"signature": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) { return otherKey, claims },
		"issuer": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			claims["iss"] = "https://other.example"
			return key, claims
		},
		"profile": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			claims["eat_profile"] = "other-profile"
			return key, claims
		},
		"expired": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			claims["exp"] = now.Unix()
			return key, claims
		},
		"missing issued at": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			delete(claims, "iat")
			return key, claims
		},
		"status": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			cpu := claims["submods"].(map[string]any)["cpu0"].(map[string]any)
			cpu["ear.status"] = "contraindicated"
			return key, claims
		},
		"policy": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			cpu := claims["submods"].(map[string]any)["cpu0"].(map[string]any)
			cpu["ear.appraisal-policy-id"] = "other-policy"
			return key, claims
		},
		"report data": func(claims map[string]any) (*ecdsa.PrivateKey, map[string]any) {
			cpu := claims["submods"].(map[string]any)["cpu0"].(map[string]any)
			annotated := cpu["ear.veraison.annotated-evidence"].(map[string]any)
			annotated["report_data"] = strings.Repeat("00", 64)
			return key, claims
		},
	}

	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				signingKey, claims := mutate(validClaims(now, runtimeData))
				_, _ = writer.Write([]byte(signEAR(t, signingKey, claims)))
			}))
			defer server.Close()

			client := testClient(server, key, now)
			if _, err := client.VerifyNode(context.Background(), VerifyInput{Quote: []byte{1}, RuntimeData: runtimeData}); err == nil {
				t.Fatalf("invalid %s EAR was accepted", name)
			}
		})
	}
}

func TestVerifyNodeDoesNotRetryTrusteeFailure(t *testing.T) {
	key := newSigningKey(t)
	postCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		postCount++
		writer.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	client := testClient(server, key, time.Now())
	if _, err := client.VerifyNode(context.Background(), VerifyInput{Quote: []byte{1}, RuntimeData: []byte{2}}); err == nil {
		t.Fatal("Trustee failure was accepted")
	}
	if postCount != 1 {
		t.Fatalf("POST count = %d, want 1", postCount)
	}
}

func testClient(server *httptest.Server, key *ecdsa.PrivateKey, now time.Time) *Client {
	return &Client{
		httpClient:       server.Client(),
		attestationURL:   server.URL + "/attestation",
		earPublicKey:     &key.PublicKey,
		expectedIssuer:   testIssuer,
		expectedProfile:  testProfile,
		policyID:         testPolicyID,
		maxResponseBytes: 1 << 20,
		now:              func() time.Time { return now },
	}
}

func assertTrusteeRequest(t *testing.T, contents, quote, runtimeData []byte) {
	t.Helper()
	var request struct {
		VerificationRequests []struct {
			TEE         string `json:"tee"`
			Evidence    string `json:"evidence"`
			RuntimeData struct {
				Raw string `json:"raw"`
			} `json:"runtime_data"`
			RuntimeDataHashAlgorithm string `json:"runtime_data_hash_algorithm"`
		} `json:"verification_requests"`
		PolicyIDs []string `json:"policy_ids"`
	}
	if err := json.Unmarshal(contents, &request); err != nil {
		t.Fatal(err)
	}
	if len(request.VerificationRequests) != 1 || len(request.PolicyIDs) != 1 {
		t.Fatalf("request = %s", contents)
	}
	verification := request.VerificationRequests[0]
	if verification.TEE != "tdx" || verification.RuntimeDataHashAlgorithm != "sha384" || request.PolicyIDs[0] != testPolicyID {
		t.Fatalf("request metadata = %#v", request)
	}
	innerBytes, err := base64.RawURLEncoding.DecodeString(verification.Evidence)
	if err != nil {
		t.Fatal(err)
	}
	var inner struct {
		CCEventLog any    `json:"cc_eventlog"`
		Quote      string `json:"quote"`
	}
	if err := json.Unmarshal(innerBytes, &inner); err != nil {
		t.Fatal(err)
	}
	if inner.CCEventLog != nil || inner.Quote != base64.StdEncoding.EncodeToString(quote) {
		t.Fatalf("inner evidence = %s", innerBytes)
	}
	raw, err := base64.RawURLEncoding.DecodeString(verification.RuntimeData.Raw)
	reportDigest := sha512.Sum384(runtimeData)
	expectedReportData := make([]byte, 64)
	copy(expectedReportData, reportDigest[:])
	if err != nil || !bytes.Equal(raw, expectedReportData) {
		t.Fatalf("runtime data = %x, want REPORTDATA %x, err = %v", raw, expectedReportData, err)
	}
}

func validClaims(now time.Time, runtimeData []byte) map[string]any {
	reportDigest := sha512.Sum384(runtimeData)
	reportData := append(reportDigest[:], make([]byte, 16)...)
	return map[string]any{
		"eat_profile": testProfile,
		"iss":         testIssuer,
		"iat":         now.Add(-time.Second).Unix(),
		"exp":         now.Add(time.Minute).Unix(),
		"submods": map[string]any{
			"cpu0": map[string]any{
				"ear.status":              "affirming",
				"ear.appraisal-policy-id": testPolicyID,
				"ear.veraison.annotated-evidence": map[string]any{
					"report_data": hex.EncodeToString(reportData),
				},
			},
		},
	}
}

func newSigningKey(t *testing.T) *ecdsa.PrivateKey {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	return key
}

func signEAR(t *testing.T, key *ecdsa.PrivateKey, claims map[string]any) string {
	t.Helper()
	header, err := json.Marshal(map[string]any{"alg": "ES256", "typ": "JWT"})
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(claims)
	if err != nil {
		t.Fatal(err)
	}
	encodedHeader := base64.RawURLEncoding.EncodeToString(header)
	encodedPayload := base64.RawURLEncoding.EncodeToString(payload)
	signingInput := encodedHeader + "." + encodedPayload
	digest := sha256.Sum256([]byte(signingInput))
	r, s, err := ecdsa.Sign(rand.Reader, key, digest[:])
	if err != nil {
		t.Fatal(err)
	}
	signature := make([]byte, 64)
	r.FillBytes(signature[:32])
	s.FillBytes(signature[32:])
	return fmt.Sprintf("%s.%s", signingInput, base64.RawURLEncoding.EncodeToString(signature))
}
