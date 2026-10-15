package broker

import (
	"bytes"
	"crypto"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	api "github.com/spiffe/go-spiffe/v2/exp/proto/spiffe/broker"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"slices"
	"time"
)

// Credentials contains one validated certificate/key/bundle generation.
// Expires is bounded by the earliest certificate expiry in its chain.
type Credentials struct {
	Certificate, Key, Bundle []byte
	Expires                  time.Time
	Serial                   string
}

// Every message is a full snapshot. Absence or duplication is a removal/error,
// never permission to retain credentials from a previous message.
func Snapshot(r *api.SubscribeToX509SVIDResponse, expected spiffeid.ID, now time.Time) (*Credentials, error) {
	var selected *api.X509SVID
	for _, s := range r.GetSvids() {
		if s.GetSpiffeId() == expected.String() {
			if selected != nil {
				return nil, fmt.Errorf("duplicate target SVID")
			}
			selected = s
		}
	}
	if selected == nil {
		return nil, fmt.Errorf("target identity removed")
	}
	certs, err := x509.ParseCertificates(selected.GetX509Svid())
	if err != nil || len(certs) == 0 {
		return nil, fmt.Errorf("invalid target certificate")
	}
	b, err := x509bundle.ParseRaw(expected.TrustDomain(), selected.GetBundle())
	if err != nil {
		return nil, err
	}
	id, _, err := x509svid.Verify(certs, b, x509svid.WithTime(now))
	if err != nil {
		return nil, err
	}
	if id != expected {
		return nil, fmt.Errorf("target SPIFFE ID mismatch")
	}
	if certs[0].KeyUsage&x509.KeyUsageDigitalSignature == 0 || !slices.Contains(certs[0].ExtKeyUsage, x509.ExtKeyUsageClientAuth) || !slices.Contains(certs[0].ExtKeyUsage, x509.ExtKeyUsageServerAuth) {
		return nil, fmt.Errorf("invalid target X.509-SVID key usages")
	}
	// Validate the key pair before any material reaches the ingress publisher;
	// matching the SPIFFE ID alone does not establish certificate/key consistency.
	key, err := x509.ParsePKCS8PrivateKey(selected.GetX509SvidKey())
	if err != nil {
		return nil, err
	}
	signer, ok := key.(crypto.Signer)
	if !ok {
		return nil, fmt.Errorf("target key is not a signer")
	}
	pub, err := x509.MarshalPKIXPublicKey(signer.Public())
	if err != nil {
		return nil, err
	}
	certPub, err := x509.MarshalPKIXPublicKey(certs[0].PublicKey)
	if err != nil || !bytes.Equal(pub, certPub) {
		return nil, fmt.Errorf("certificate/key mismatch")
	}
	c := &Credentials{Key: pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: selected.GetX509SvidKey()}), Expires: certs[0].NotAfter, Serial: certs[0].SerialNumber.String()}
	for _, cert := range certs {
		c.Certificate = append(c.Certificate, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Raw})...)
		if cert.NotAfter.Before(c.Expires) {
			c.Expires = cert.NotAfter
		}
	}
	c.Bundle, err = b.Marshal()
	return c, err
}
