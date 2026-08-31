package agent

import (
	"bytes"
	"crypto/ed25519"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestLoadProofKeyReadsPKCS8PEMEd25519(t *testing.T) {
	privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x42}, ed25519.SeedSize))
	der, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	contents := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})
	path := filepath.Join(t.TempDir(), "proof-key.pem")
	if err := os.WriteFile(path, contents, 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := loadProofKey(path)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, privateKey) {
		t.Fatal("loaded key differs from provisioned key")
	}
}

func TestLoadProofKeyIsLoadOnly(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing.pem")
	if _, err := loadProofKey(path); !os.IsNotExist(err) {
		t.Fatalf("missing key error = %v", err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("missing key was created")
	}
}

func TestLoadProofKeyRejectsRawAndBroadlyReadableFiles(t *testing.T) {
	for name, mode := range map[string]os.FileMode{
		"raw":         0o600,
		"permissions": 0o644,
	} {
		t.Run(name, func(t *testing.T) {
			if name == "permissions" && runtime.GOOS == "windows" {
				t.Skip("Windows file modes do not represent Unix 0600 permissions")
			}
			path := filepath.Join(t.TempDir(), "proof-key.pem")
			if err := os.WriteFile(path, make([]byte, ed25519.PrivateKeySize), mode); err != nil {
				t.Fatal(err)
			}
			if _, err := loadProofKey(path); err == nil {
				t.Fatal("invalid proof key file was accepted")
			}
		})
	}
}
