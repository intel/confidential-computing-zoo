// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package protocol

import (
	"crypto/sha256"
	"crypto/sha512"
	"encoding/binary"
	"encoding/hex"
	"fmt"
)

// NodeRuntimeData returns the canonical bytes shared by the Rust Provider and
// the Server-side Trustee request. Length prefixes keep the identity fields
// unambiguous before the fixed-size nonce and proof key.
func NodeRuntimeData(agentID string, nonce, proofPublicKey []byte) ([]byte, error) {
	if _, err := AgentTrustDomain(agentID); err != nil {
		return nil, err
	}
	if len(nonce) != NonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes", NonceSize)
	}
	if len(proofPublicKey) != PublicKeySize {
		return nil, fmt.Errorf("proof public key must be %d bytes", PublicKeySize)
	}

	runtimeData := make([]byte, 0, 2+len(reportDataDomain)+2+len(agentID)+NonceSize+PublicKeySize)
	runtimeData = appendLP16(runtimeData, []byte(reportDataDomain))
	runtimeData = appendLP16(runtimeData, []byte(agentID))
	runtimeData = append(runtimeData, nonce...)
	runtimeData = append(runtimeData, proofPublicKey...)
	return runtimeData, nil
}

// ReportData maps NodeRuntimeData into TDX REPORTDATA as SHA-384 followed by a
// zero-filled 16-byte tail.
func ReportData(agentID string, nonce, proofPublicKey []byte) ([64]byte, error) {
	var reportData [64]byte
	runtimeData, err := NodeRuntimeData(agentID, nonce, proofPublicKey)
	if err != nil {
		return reportData, err
	}
	digest := sha512.Sum384(runtimeData)
	copy(reportData[:48], digest[:])
	return reportData, nil
}

// TranscriptDigest binds proof-of-possession to the exact challenge window and
// Quote bytes. It complements hardware REPORTDATA binding; it does not appraise
// the Quote.
func TranscriptDigest(proofPublicKey, nonce []byte, expiresAtUnixMs uint64, tdxQuote []byte) ([64]byte, error) {
	var result [64]byte
	if len(proofPublicKey) != PublicKeySize {
		return result, fmt.Errorf("proof public key must be %d bytes", PublicKeySize)
	}
	if len(nonce) != NonceSize {
		return result, fmt.Errorf("nonce must be %d bytes", NonceSize)
	}
	if len(tdxQuote) == 0 {
		return result, fmt.Errorf("TDX Quote is required")
	}

	quoteDigest := sha256.Sum256(tdxQuote)
	transcript := make([]byte, 0, 2+len(transcriptDomain)+PublicKeySize+NonceSize+8+sha256.Size)
	transcript = appendLP16(transcript, []byte(transcriptDomain))
	transcript = append(transcript, proofPublicKey...)
	transcript = append(transcript, nonce...)
	expiresAt := make([]byte, 8)
	binary.BigEndian.PutUint64(expiresAt, expiresAtUnixMs)
	transcript = append(transcript, expiresAt...)
	transcript = append(transcript, quoteDigest[:]...)
	return sha512.Sum512(transcript), nil
}

// KeyID returns the lowercase SHA-256 fingerprint used to pin an Agent slot.
func KeyID(proofPublicKey []byte) (string, error) {
	if len(proofPublicKey) != PublicKeySize {
		return "", fmt.Errorf("proof public key must be %d bytes", PublicKeySize)
	}
	digest := sha256.Sum256(proofPublicKey)
	return hex.EncodeToString(digest[:]), nil
}

func appendLP16(destination, value []byte) []byte {
	length := make([]byte, 2)
	binary.BigEndian.PutUint16(length, uint16(len(value)))
	destination = append(destination, length...)
	return append(destination, value...)
}
