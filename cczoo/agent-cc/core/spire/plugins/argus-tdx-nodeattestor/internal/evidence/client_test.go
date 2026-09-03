package evidence

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (roundTrip roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return roundTrip(request)
}

func TestGetNodeEvidenceUsesTypedNodeEndpoint(t *testing.T) {
	nonce := bytes.Repeat([]byte{0x11}, protocol.NonceSize)
	publicKey := bytes.Repeat([]byte{0x22}, protocol.PublicKeySize)
	quote := []byte{0x01, 0x02, 0x03, 0xff}

	client := &Client{
		httpClient: &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			if request.Method != http.MethodPost {
				t.Errorf("method = %s", request.Method)
			}
			if request.URL.Path != "/node-evidence" {
				t.Errorf("path = %s", request.URL.Path)
			}
			if request.Header.Get("Content-Type") != "application/json" {
				t.Errorf("Content-Type = %q", request.Header.Get("Content-Type"))
			}
			var body nodeEvidenceRequest
			if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
				t.Fatal(err)
			}
			if body.Nonce != base64.RawURLEncoding.EncodeToString(nonce) {
				t.Errorf("nonce = %q", body.Nonce)
			}
			if body.ProofPublicKey != base64.RawURLEncoding.EncodeToString(publicKey) {
				t.Errorf("proof public key = %q", body.ProofPublicKey)
			}
			response := `{"evidence_type":"tdx_quote","quote_format":"tdx","quote":"` + base64.RawURLEncoding.EncodeToString(quote) + `"}`
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader(response)),
				Header:     make(http.Header),
			}, nil
		})},
		requestURL: "http://unix/node-evidence",
		maxBytes:   1024,
	}

	got, err := client.GetNodeEvidence(context.Background(), nonce, publicKey)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, quote) {
		t.Fatalf("quote = %x, want %x", got, quote)
	}
}

func TestGetNodeEvidenceRejectsInvalidProviderResponses(t *testing.T) {
	validQuote := base64.RawURLEncoding.EncodeToString([]byte{1})
	for name, test := range map[string]struct {
		statusCode int
		body       string
	}{
		"status":         {statusCode: http.StatusServiceUnavailable},
		"evidence type":  {statusCode: http.StatusOK, body: `{"evidence_type":"other","quote_format":"tdx","quote":"` + validQuote + `"}`},
		"quote format":   {statusCode: http.StatusOK, body: `{"evidence_type":"tdx_quote","quote_format":"other","quote":"` + validQuote + `"}`},
		"unknown field":  {statusCode: http.StatusOK, body: `{"evidence_type":"tdx_quote","quote_format":"tdx","quote":"` + validQuote + `","other":true}`},
		"invalid quote":  {statusCode: http.StatusOK, body: `{"evidence_type":"tdx_quote","quote_format":"tdx","quote":"***"}`},
		"empty quote":    {statusCode: http.StatusOK, body: `{"evidence_type":"tdx_quote","quote_format":"tdx","quote":""}`},
		"oversize quote": {statusCode: http.StatusOK, body: `{"evidence_type":"tdx_quote","quote_format":"tdx","quote":"` + base64.RawURLEncoding.EncodeToString([]byte{1, 2}) + `"}`},
	} {
		t.Run(name, func(t *testing.T) {
			client := &Client{
				httpClient: &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
					return &http.Response{StatusCode: test.statusCode, Body: io.NopCloser(strings.NewReader(test.body)), Header: make(http.Header)}, nil
				})},
				requestURL: "http://unix/node-evidence",
				maxBytes:   1,
			}
			if _, err := client.GetNodeEvidence(context.Background(), make([]byte, protocol.NonceSize), make([]byte, protocol.PublicKeySize)); err == nil {
				t.Fatal("invalid Provider response was accepted")
			}
		})
	}
}

func TestNewClientRequiresAbsoluteUnixSocketAndLimits(t *testing.T) {
	client, err := NewClient("/run/argus/evidence-provider.sock", time.Second, 1)
	if err != nil {
		t.Fatal(err)
	}
	transport := client.httpClient.Transport.(*http.Transport)
	if transport.Proxy != nil {
		t.Fatal("Unix-socket client retained environment proxy routing")
	}
	if _, err := NewClient("relative.sock", time.Second, 1); err == nil {
		t.Fatal("relative socket path was accepted")
	}
	if _, err := NewClient("/run/argus/evidence-provider.sock", 0, 1); err == nil {
		t.Fatal("zero timeout was accepted")
	}
	if _, err := NewClient("/run/argus/evidence-provider.sock", time.Second, 0); err == nil {
		t.Fatal("zero quote size was accepted")
	}
	if _, err := NewClient("/run/argus/evidence-provider.sock", time.Second, protocol.MaxQuoteSize+1); err == nil {
		t.Fatal("oversize quote limit was accepted")
	}
}

func TestGetNodeEvidenceRejectsInvalidRequestLengths(t *testing.T) {
	client := &Client{httpClient: http.DefaultClient, requestURL: "http://unix/node-evidence", maxBytes: 1}
	if _, err := client.GetNodeEvidence(context.Background(), make([]byte, protocol.NonceSize-1), make([]byte, protocol.PublicKeySize)); err == nil {
		t.Fatal("invalid nonce was accepted")
	}
	if _, err := client.GetNodeEvidence(context.Background(), make([]byte, protocol.NonceSize), make([]byte, protocol.PublicKeySize-1)); err == nil {
		t.Fatal("invalid proof public key was accepted")
	}
}
