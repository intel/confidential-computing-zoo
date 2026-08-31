package protocol

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"
)

type bindingGolden struct {
	AgentID            string `json:"agent_id"`
	NonceHex           string `json:"nonce_hex"`
	ProofPublicKeyHex  string `json:"proof_public_key_hex"`
	NodeRuntimeDataHex string `json:"node_runtime_data_hex"`
	ReportDataHex      string `json:"report_data_hex"`
}

func TestNodeBindingGoldenVector(t *testing.T) {
	contents, err := os.ReadFile("testdata/report-data.json")
	if err != nil {
		t.Fatal(err)
	}
	var vector bindingGolden
	decoder := json.NewDecoder(bytes.NewReader(contents))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&vector); err != nil {
		t.Fatal(err)
	}
	if vector.AgentID != FixedAgentSPIFFEID {
		t.Fatalf("Agent ID = %q, want %q", vector.AgentID, FixedAgentSPIFFEID)
	}
	nonce, err := hex.DecodeString(vector.NonceHex)
	if err != nil {
		t.Fatal(err)
	}
	publicKey, err := hex.DecodeString(vector.ProofPublicKeyHex)
	if err != nil {
		t.Fatal(err)
	}

	runtimeData, err := NodeRuntimeData(nonce, publicKey)
	if err != nil {
		t.Fatal(err)
	}
	if got := hex.EncodeToString(runtimeData); got != vector.NodeRuntimeDataHex {
		t.Fatalf("node runtime data = %s, want %s", got, vector.NodeRuntimeDataHex)
	}

	reportData, err := ReportData(nonce, publicKey)
	if err != nil {
		t.Fatal(err)
	}
	if got := hex.EncodeToString(reportData[:]); got != vector.ReportDataHex {
		t.Fatalf("REPORTDATA = %s, want %s", got, vector.ReportDataHex)
	}
	if !bytes.Equal(reportData[48:], make([]byte, 16)) {
		t.Fatal("REPORTDATA trailing 16 bytes are not zero")
	}
}

func TestTranscriptDigestGoldenVector(t *testing.T) {
	nonce := sequentialBytes(0x00, NonceSize)
	publicKey := sequentialBytes(0x20, PublicKeySize)
	quote := []byte{0x54, 0x44, 0x58, 0x00, 0xff}

	digest, err := TranscriptDigest(publicKey, nonce, 1_700_000_000_123, quote)
	if err != nil {
		t.Fatal(err)
	}
	const expected = "8103a2f51685a571c0990cd894962487effbabfd91d5474497c3f671bb1a1e62862de1461397f19a9ea38cbba36a0e06910e857b507867f4654708a286c98bd9"
	if got := hex.EncodeToString(digest[:]); got != expected {
		t.Fatalf("transcript digest = %s, want %s", got, expected)
	}
}

func TestBindingRejectsInvalidLengths(t *testing.T) {
	validNonce := make([]byte, NonceSize)
	validKey := make([]byte, PublicKeySize)

	for name, operation := range map[string]func() error{
		"runtime nonce": func() error { _, err := NodeRuntimeData(validNonce[:31], validKey); return err },
		"runtime key":   func() error { _, err := NodeRuntimeData(validNonce, validKey[:31]); return err },
		"report nonce":  func() error { _, err := ReportData(validNonce[:31], validKey); return err },
		"transcript key": func() error {
			_, err := TranscriptDigest(validKey[:31], validNonce, 1, []byte{1})
			return err
		},
		"empty quote": func() error { _, err := TranscriptDigest(validKey, validNonce, 1, nil); return err },
	} {
		t.Run(name, func(t *testing.T) {
			if err := operation(); err == nil {
				t.Fatal("invalid input was accepted")
			}
		})
	}
}

func sequentialBytes(start byte, size int) []byte {
	result := make([]byte, size)
	for index := range result {
		result[index] = start + byte(index)
	}
	return result
}
