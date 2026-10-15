package disk

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"io/fs"
	"os"
	"path"
	"time"

	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

// WriteX509Context takes a X509Context, representing a svid message from
// the Workload API, and calls writeCerts and writeKey to write to disk
// the svid, key and bundle of certificates.
// It is possible to change output setting `addIntermediatesToBundle` as true.
func WriteX509Context(x509Context *workloadapi.X509Context, addIntermediatesToBundle, includeFederatedDomains, omitExpired bool, certDir, svidFilename, svidKeyFilename, svidBundleFilename string, certFileMode, keyFileMode fs.FileMode, hint string) error {
	svidFile := path.Join(certDir, svidFilename)
	svidKeyFile := path.Join(certDir, svidKeyFilename)
	svidBundleFile := path.Join(certDir, svidBundleFilename)

	svid, err := getX509SVID(x509Context, hint)
	if err != nil {
		return err
	}

	// Extract bundle for the default SVID
	bundleSet, found := x509Context.Bundles.Get(svid.ID.TrustDomain())
	if !found {
		return fmt.Errorf("no bundles found for %q trust domain", svid.ID.TrustDomain().String())
	}
	bundles := bundleSet.X509Authorities()

	// Extract private key
	privateKey, err := x509.MarshalPKCS8PrivateKey(svid.PrivateKey)
	if err != nil {
		return err
	}

	// Add intermediates into bundles and remove them from certs
	certs := svid.Certificates
	if addIntermediatesToBundle {
		bundles = append(bundles, certs[1:]...)
		certs = []*x509.Certificate{certs[0]}
	}

	// If using federated domains, add them to the CA bundle
	if includeFederatedDomains {
		for _, bundle := range x509Context.Bundles.Bundles() {
			// The bundle corresponding to svid.ID.TrustDomain is already stored
			if bundle.TrustDomain().Name() != svid.ID.TrustDomain().Name() {
				bundles = append(bundles, bundle.X509Authorities()...)
			}
		}
	}

	// Write cert, key, and bundle to disk
	if err := writeCerts(svidFile, certs, certFileMode, omitExpired); err != nil {
		return err
	}

	if err := writeKey(svidKeyFile, privateKey, keyFileMode); err != nil {
		return err
	}

	return writeCerts(svidBundleFile, bundles, certFileMode, omitExpired)
}

// writeCerts takes an array of certificates,
// and encodes them as PEM blocks, writing them to file
func writeCerts(file string, certs []*x509.Certificate, certFileMode fs.FileMode, omitExpired bool) error {
	var pemData []byte
	for _, cert := range certs {
		if omitExpired && time.Now().UTC().After(cert.NotAfter) {
			continue
		}
		b := &pem.Block{
			Type:  "CERTIFICATE",
			Bytes: cert.Raw,
		}
		pemData = append(pemData, pem.EncodeToMemory(b)...)
	}

	return os.WriteFile(file, pemData, certFileMode)
}

// writeKey takes a private key as a slice of bytes,
// formats as PEM, and writes it to file
func writeKey(file string, data []byte, keyFileMode fs.FileMode) error {
	b := &pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: data,
	}

	return os.WriteFile(file, pem.EncodeToMemory(b), keyFileMode)
}

// getX509SVID extracts the x509 SVID that matches the hint or returns the default
// if hint is empty
func getX509SVID(x509Context *workloadapi.X509Context, hint string) (*x509svid.SVID, error) {
	if hint == "" {
		return x509Context.DefaultSVID(), nil
	}

	for _, svid := range x509Context.SVIDs {
		if svid.Hint == hint {
			return svid, nil
		}
	}

	return nil, fmt.Errorf("failed to find the hinted x509 SVID")
}
