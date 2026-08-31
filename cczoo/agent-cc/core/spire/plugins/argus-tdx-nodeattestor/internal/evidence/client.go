// Package evidence connects the Agent NodeAttestor to the guest-local TDX
// Evidence Provider. The Unix socket is the local trust boundary; this client
// transports raw evidence but does not appraise it.
package evidence

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"path"
	"time"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-nodeattestor/internal/protocol"
)

const nodeEvidenceURL = "http://unix/node-evidence"

type nodeEvidenceRequest struct {
	Nonce          string `json:"nonce"`
	ProofPublicKey string `json:"proof_public_key"`
}

type nodeEvidenceResponse struct {
	EvidenceType string `json:"evidence_type"`
	QuoteFormat  string `json:"quote_format"`
	Quote        string `json:"quote"`
}

// Client calls the typed Node Evidence endpoint over a Unix domain socket.
type Client struct {
	httpClient *http.Client
	requestURL string
	maxBytes   int64
}

// NewClient constructs a bounded guest-local Evidence Provider client.
func NewClient(socketPath string, timeout time.Duration, maxQuoteBytes int64) (*Client, error) {
	if !path.IsAbs(socketPath) {
		return nil, fmt.Errorf("evidence socket path must be absolute")
	}
	if timeout <= 0 {
		return nil, fmt.Errorf("evidence timeout must be positive")
	}
	if maxQuoteBytes <= 0 || maxQuoteBytes > protocol.MaxQuoteSize {
		return nil, fmt.Errorf("maximum Quote size must be between 1 and %d bytes", protocol.MaxQuoteSize)
	}

	transport := http.DefaultTransport.(*http.Transport).Clone()
	// Never route guest-local evidence through an HTTP proxy; the URL host is a
	// placeholder and every connection is forced onto the configured UDS.
	transport.Proxy = nil
	transport.DialContext = func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socketPath)
	}
	return &Client{
		httpClient: &http.Client{Transport: transport, Timeout: timeout},
		requestURL: nodeEvidenceURL,
		maxBytes:   maxQuoteBytes,
	}, nil
}

// GetNodeEvidence asks the Provider for a Quote bound to one Server nonce and
// the Agent proof public key.
func (client *Client) GetNodeEvidence(ctx context.Context, nonce, proofPublicKey []byte) ([]byte, error) {
	if len(nonce) != protocol.NonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes", protocol.NonceSize)
	}
	if len(proofPublicKey) != protocol.PublicKeySize {
		return nil, fmt.Errorf("proof public key must be %d bytes", protocol.PublicKeySize)
	}

	requestBody, err := json.Marshal(nodeEvidenceRequest{
		Nonce:          base64.RawURLEncoding.EncodeToString(nonce),
		ProofPublicKey: base64.RawURLEncoding.EncodeToString(proofPublicKey),
	})
	if err != nil {
		return nil, fmt.Errorf("marshal node evidence request: %w", err)
	}
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodPost, client.requestURL, bytes.NewReader(requestBody))
	if err != nil {
		return nil, fmt.Errorf("create node evidence request: %w", err)
	}
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Accept", "application/json")

	response, err := client.httpClient.Do(httpRequest)
	if err != nil {
		return nil, fmt.Errorf("request node evidence: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return nil, fmt.Errorf("Evidence Provider returned HTTP %d", response.StatusCode)
	}

	// Base64URL expands the Quote, while the fixed allowance covers the small
	// JSON envelope without permitting an unbounded response body.
	maximumResponseBytes := client.maxBytes*2 + 1024
	contents, err := io.ReadAll(io.LimitReader(response.Body, maximumResponseBytes+1))
	if err != nil {
		return nil, fmt.Errorf("read node evidence response: %w", err)
	}
	if int64(len(contents)) > maximumResponseBytes {
		return nil, fmt.Errorf("node evidence response exceeds the configured limit")
	}
	decoder := json.NewDecoder(bytes.NewReader(contents))
	decoder.DisallowUnknownFields()
	var result nodeEvidenceResponse
	if err := decoder.Decode(&result); err != nil {
		return nil, fmt.Errorf("decode node evidence response: %w", err)
	}
	var extra json.RawMessage
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("node evidence response contains multiple JSON values")
		}
		return nil, fmt.Errorf("decode node evidence response: %w", err)
	}
	if result.EvidenceType != "tdx_quote" {
		return nil, fmt.Errorf("Evidence Provider evidence_type must be tdx_quote")
	}
	if result.QuoteFormat != "tdx" {
		return nil, fmt.Errorf("Evidence Provider quote_format must be tdx")
	}
	quote, err := base64.RawURLEncoding.DecodeString(result.Quote)
	if err != nil {
		return nil, fmt.Errorf("decode TDX Quote: %w", err)
	}
	if len(quote) == 0 || int64(len(quote)) > client.maxBytes {
		return nil, fmt.Errorf("TDX Quote size is outside the allowed range")
	}
	return quote, nil
}
