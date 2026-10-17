package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"io"
	"net"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

// headerBindings declares application headers by environment-variable name.
// No application's API key is discovered implicitly or passed in flag values.
type headerBindings map[string]string

func (h *headerBindings) String() string { return "header-to-environment bindings" }
func (h *headerBindings) Set(value string) error {
	name, variable, ok := strings.Cut(value, "=")
	if !ok || !regexp.MustCompile("^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$").MatchString(name) || !regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]{0,127}$`).MatchString(variable) {
		return fmt.Errorf("header-env must be HEADER=ENV_VAR")
	}
	name = http.CanonicalHeaderKey(name)
	if *h == nil {
		*h = make(headerBindings)
	}
	if _, exists := (*h)[name]; exists || len(*h) >= 32 {
		return fmt.Errorf("duplicate or excessive header-env binding")
	}
	(*h)[name] = variable
	return nil
}

func (h headerBindings) apply(req *http.Request) error {
	for name, variable := range h {
		value, exists := os.LookupEnv(variable)
		if !exists || value == "" || len(value) > 8192 || strings.ContainsAny(value, "\r\n\x00") {
			return fmt.Errorf("missing or invalid environment value for configured header %s", name)
		}
		req.Header.Set(name, value)
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	cert := flag.String("cert", "", "client SVID PEM")
	key := flag.String("key", "", "client key PEM")
	bundle := flag.String("bundle", "", "trust bundle PEM")
	target := flag.String("server-id", "", "required exact server SPIFFE ID")
	endpoint := flag.String("url", "", "HTTPS business endpoint")
	tlsOnly := flag.Bool("tls-only", false, "check that NGINX loaded the certificate given in -cert")
	var headers headerBindings
	flag.Var(&headers, "header-env", "business request header from environment: HEADER=ENV_VAR (repeatable)")
	flag.Parse()
	id, err := spiffeid.FromString(*target)
	if err != nil {
		return err
	}
	s, err := x509svid.Load(*cert, *key)
	if err != nil {
		return err
	}
	b, err := x509bundle.Load(id.TrustDomain(), *bundle)
	if err != nil {
		return err
	}
	tlsConfig := tlsconfig.MTLSClientConfig(s, b, tlsconfig.AuthorizeID(id))
	tlsConfig.ClientSessionCache = nil
	client := &http.Client{Transport: &http.Transport{TLSClientConfig: tlsConfig, DisableKeepAlives: true}, Timeout: 15 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	req, err := http.NewRequest("GET", *endpoint, nil)
	if err != nil {
		return err
	}
	if req.URL.Scheme != "https" {
		return fmt.Errorf("HTTPS URL required")
	}
	if *tlsOnly {
		// The publication hook supplies the server generation here to check that
		// NGINX loaded that exact leaf. This performs no business HTTP request.
		deadline := time.Now().Add(3 * time.Second)
		for {
			conn, err := tls.DialWithDialer(&net.Dialer{Timeout: time.Second}, "tcp", req.URL.Host, tlsConfig)
			if err == nil {
				loaded := bytes.Equal(conn.ConnectionState().PeerCertificates[0].Raw, s.Certificates[0].Raw)
				_ = conn.Close()
				if loaded {
					return nil
				}
			}
			if !time.Now().Before(deadline) {
				return fmt.Errorf("NGINX did not load the published certificate")
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	// Only explicitly configured credentials are read; values stay out of argv.
	if err := headers.apply(req); err != nil {
		return err
	}
	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	_, err = io.Copy(io.Discard, io.LimitReader(res.Body, 1<<20))
	if err != nil {
		return err
	}
	if res.StatusCode < 200 || res.StatusCode >= 300 {
		return fmt.Errorf("business HTTP %d", res.StatusCode)
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"result": "PASS", "client_spiffe_id": s.ID.String(), "server_spiffe_id": id.String(), "server_serial": res.TLS.PeerCertificates[0].SerialNumber.String(), "http_status": res.StatusCode, "checked_at": time.Now().UTC()})
}
