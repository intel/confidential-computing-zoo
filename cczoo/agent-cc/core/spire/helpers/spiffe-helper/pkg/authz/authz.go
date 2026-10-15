// Package authz checks the TLS peer identity reported by trusted NGINX.
// Deployment must expose the handler only through the protected local UDS and
// overwrite both input headers from NGINX's TLS connection. NGINX verifies the
// chain; this package checks the reported result, SVID profile and exact peer ID.
package authz

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"net/http"
	"net/url"
	"slices"
	"strings"
	"time"
)

func Authorize(escapedPEM, verifyStatus string, expected spiffeid.ID, now time.Time) error {
	return AuthorizeAny(escapedPEM, verifyStatus, []spiffeid.ID{expected}, now)
}

// AuthorizeAny allows only exact members of a nonempty identity set. No prefix
// matching is used: service identity is independent of business API keys.
func AuthorizeAny(escapedPEM, verifyStatus string, allowed []spiffeid.ID, now time.Time) error {
	if verifyStatus != "SUCCESS" {
		return fmt.Errorf("NGINX did not verify the TLS client chain")
	}
	if len(escapedPEM) > 32768 {
		return fmt.Errorf("certificate too large")
	}
	decoded, err := url.PathUnescape(escapedPEM)
	if err != nil {
		return err
	}
	block, rest := pem.Decode([]byte(decoded))
	if block == nil || block.Type != "CERTIFICATE" || strings.TrimSpace(string(rest)) != "" {
		return fmt.Errorf("expected exactly one peer leaf certificate")
	}
	c, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return err
	}
	id, err := x509svid.IDFromCert(c)
	if err != nil {
		return err
	}
	if !slices.Contains(allowed, id) {
		return fmt.Errorf("client SPIFFE ID denied")
	}
	if c.IsCA || c.KeyUsage&x509.KeyUsageDigitalSignature == 0 || c.KeyUsage&(x509.KeyUsageCertSign|x509.KeyUsageCRLSign) != 0 {
		return fmt.Errorf("invalid X.509-SVID key usage")
	}
	if !slices.Contains(c.ExtKeyUsage, x509.ExtKeyUsageClientAuth) || !slices.Contains(c.ExtKeyUsage, x509.ExtKeyUsageServerAuth) {
		return fmt.Errorf("X.509-SVID requires client/server extended key usages")
	}
	if now.Before(c.NotBefore) || !now.Before(c.NotAfter) {
		return fmt.Errorf("client SVID expired or not yet valid")
	}
	return nil
}
func Handler(expected spiffeid.ID) http.Handler {
	return HandlerForIDs([]spiffeid.ID{expected})
}

// HandlerForIDs freezes the operator's exact allowlist for this handler. Its
// certificate headers must be supplied by the trusted NGINX TLS connection.
func HandlerForIDs(allowed []spiffeid.ID) http.Handler {
	allowed = slices.Clone(allowed)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/authorize" || r.Method != "GET" {
			http.NotFound(w, r)
			return
		}
		if len(r.Header.Values("X-Argus-TLS-Cert")) != 1 || len(r.Header.Values("X-Argus-TLS-Verified")) != 1 {
			// Do not let duplicate headers introduce a different peer identity
			// depending on which component chooses the first or last value.
			http.Error(w, "denied", http.StatusForbidden)
			return
		}
		if err := AuthorizeAny(r.Header.Get("X-Argus-TLS-Cert"), r.Header.Get("X-Argus-TLS-Verified"), allowed, time.Now()); err != nil {
			http.Error(w, "denied", http.StatusForbidden)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})
}
