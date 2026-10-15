// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Package protocol defines the shared workload evidence and Trustee binding.
package protocol

import (
	"bytes"
	"crypto/sha512"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const Name = "argus.workload.tdx"

// Target records observations made by the trusted guest launcher/collector.
// File protection and runtime checks belong to target/ and the Provider;
// configured baselines and Trustee policy supply approval. Executable is a
// path, not a content hash. Decimal strings avoid cross-language JSON numbers.
type Target struct {
	AgentID           string `json:"agent_id"`
	BootID            string `json:"boot_id"`
	ConfigDigest      string `json:"config_digest"`
	ConfigEnv         string `json:"config_env"`
	ConfigPath        string `json:"config_path"`
	ContainerID       string `json:"container_id"`
	Executable        string `json:"executable"`
	ImageConfigDigest string `json:"image_config_digest"`
	LaunchID          string `json:"launch_id"`
	ListenPort        string `json:"listen_port"`
	NetNamespace      string `json:"net_namespace"`
	PID               string `json:"pid"`
	PIDNamespace      string `json:"pid_namespace"`
	PolicyID          string `json:"policy_id"`
	RootFSReadOnly    string `json:"rootfs_read_only"`
	StartTime         string `json:"start_time"`
	WorkloadID        string `json:"workload_id"`
}

// RuntimeData binds one fresh challenge to the complete observed instance.
// Its canonical bytes must agree with the Provider and Trustee verifier.
type RuntimeData struct {
	Target
	Nonce    string `json:"nonce"`
	Protocol string `json:"protocol"`
}

type EvidenceRequest struct {
	Protocol string `json:"protocol"`
	Nonce    string `json:"nonce"`
	PID      int32  `json:"pid"`
}

type Evidence struct {
	EvidenceType  string      `json:"evidence_type"`
	Quote         string      `json:"quote"`
	RuntimeData   RuntimeData `json:"runtime_data"`
	RekorEntryIDs []string    `json:"rekor_entry_ids"`
}

// UUIDs and decimal log indexes are retrieval references, never appraisal results.
func ValidateRekorReferences(references []string) error {
	if len(references) < 2 || len(references) > 4096 {
		return fmt.Errorf("complete bounded Rekor history is required")
	}
	seen := make(map[string]bool, len(references))
	for _, reference := range references {
		index := len(reference) > 0 && len(reference) < 64 && strings.Trim(reference, "0123456789") == ""
		uuid := (len(reference) == 64 || len(reference) == 80) && strings.Trim(reference, "0123456789abcdef") == ""
		if !(index || uuid) || seen[reference] {
			return fmt.Errorf("invalid or duplicate Rekor entry reference")
		}
		seen[reference] = true
	}
	return nil
}

var component = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
var hex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)
var bootID = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var decimal = regexp.MustCompile(`^[1-9][0-9]*$`)
var namespace = regexp.MustCompile(`^(pid|net):\[[1-9][0-9]*\]$`)
var environmentName = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]{0,127}$`)

// ValidateAgentID uses the same identity grammar as the NodeAttestor. Expected
// deployment identities are checked by consumers, independently of this schema.
func ValidateAgentID(id string) error {
	rest, ok := strings.CutPrefix(id, "spiffe://")
	domain, node, found := strings.Cut(rest, "/spire/agent/argus_tdx/")
	if !ok || !found || len(id) > 65535 || !regexp.MustCompile(`^[a-z0-9._-]+$`).MatchString(domain) || !component.MatchString(node) || strings.Trim(node, ".") == "" {
		return fmt.Errorf("invalid SPIRE Agent identity")
	}
	return nil
}

func (t Target) Validate() error {
	if !environmentName.MatchString(t.ConfigEnv) {
		return fmt.Errorf("configuration environment variable is required")
	}
	if ValidateAgentID(t.AgentID) != nil || !bootID.MatchString(t.BootID) {
		return fmt.Errorf("invalid node context")
	}
	for name, value := range map[string]string{"workload_id": t.WorkloadID, "policy_id": t.PolicyID, "launch_id": t.LaunchID} {
		if len(value) > 128 || !component.MatchString(value) {
			return fmt.Errorf("invalid %s", name)
		}
	}
	if !hex64.MatchString(t.ContainerID) || !Digest(t.ImageConfigDigest) || !Digest(t.ConfigDigest) {
		return fmt.Errorf("actual SHA-256 container/image/config identifiers are required")
	}
	pid, err := strconv.ParseInt(t.PID, 10, 32)
	if err != nil || pid <= 0 || !decimal.MatchString(t.PID) || !decimal.MatchString(t.StartTime) {
		return fmt.Errorf("invalid process instance")
	}
	port, err := strconv.ParseUint(t.ListenPort, 10, 16)
	if err != nil || port == 0 || !decimal.MatchString(t.ListenPort) {
		return fmt.Errorf("invalid listen port")
	}
	if !namespace.MatchString(t.PIDNamespace) || !strings.HasPrefix(t.PIDNamespace, "pid:") || !namespace.MatchString(t.NetNamespace) || !strings.HasPrefix(t.NetNamespace, "net:") {
		return fmt.Errorf("invalid namespace")
	}
	for _, p := range []string{t.ConfigPath, t.Executable} {
		if !path.IsAbs(p) || path.Clean(p) != p || strings.Contains(p, "\x00") {
			return fmt.Errorf("invalid target path")
		}
	}
	if t.RootFSReadOnly != "true" {
		return fmt.Errorf("read-only workload root filesystem required")
	}
	// This schema is deliberately ASCII/string-only. Its sorted compact JSON
	// is RFC 8785 compatible without numeric or UTF-16 ordering ambiguity.
	b, _ := json.Marshal(t)
	var values map[string]string
	if err := json.Unmarshal(b, &values); err != nil {
		return err
	}
	for _, v := range values {
		for _, r := range v {
			if r < 32 || r > 126 {
				return fmt.Errorf("non-ASCII target value")
			}
		}
	}
	return nil
}

func Digest(value string) bool {
	return strings.HasPrefix(value, "sha256:") && hex64.MatchString(strings.TrimPrefix(value, "sha256:"))
}

func ValidateNonce(value string) error {
	b, err := base64.RawURLEncoding.Strict().DecodeString(value)
	if err != nil || len(b) != 32 || base64.RawURLEncoding.EncodeToString(b) != value {
		return fmt.Errorf("nonce must be 32 bytes of canonical base64url without padding")
	}
	return nil
}

// Canonical emits sorted, compact JSON without HTML escaping or a trailing
// newline. These bytes, not a language-specific struct encoding, are hashed.
func (d RuntimeData) Canonical() ([]byte, error) {
	if d.Protocol != Name {
		return nil, fmt.Errorf("unsupported workload protocol")
	}
	if err := d.Target.Validate(); err != nil {
		return nil, err
	}
	if err := ValidateNonce(d.Nonce); err != nil {
		return nil, err
	}
	b, err := json.Marshal(d)
	if err != nil {
		return nil, err
	}
	var fields map[string]string
	if err = json.Unmarshal(b, &fields); err != nil {
		return nil, err
	}
	var out bytes.Buffer
	enc := json.NewEncoder(&out)
	enc.SetEscapeHTML(false)
	if err = enc.Encode(fields); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(out.Bytes(), []byte{'\n'}), nil
}

// ReportData places the SHA-384 digest in the first 48 bytes of TDX REPORTDATA;
// the remaining 16 bytes stay zero, matching Trustee's structured-data binding.
func (d RuntimeData) ReportData() ([64]byte, error) {
	var result [64]byte
	b, err := d.Canonical()
	if err != nil {
		return result, err
	}
	sum := sha512.Sum384(b)
	copy(result[:48], sum[:])
	return result, nil
}

// Validate checks envelope shape and exact request/target binding. It does not
// authenticate the Quote or appraise its platform; that requires Trustee/EAR.
func (e Evidence) Validate(request EvidenceRequest, target Target) error {
	if err := ValidateRekorReferences(e.RekorEntryIDs); err != nil {
		return err
	}
	if request.Protocol != Name || e.EvidenceType != "tdx_quote" || e.RuntimeData.Protocol != Name || e.RuntimeData.Nonce != request.Nonce || e.RuntimeData.Target != target || target.PID != strconv.FormatInt(int64(request.PID), 10) {
		return fmt.Errorf("workload evidence does not match request and registered instance")
	}
	if _, err := e.RuntimeData.ReportData(); err != nil {
		return err
	}
	q, err := base64.RawURLEncoding.Strict().DecodeString(e.Quote)
	if err != nil || len(q) == 0 || len(q) > 1<<20 {
		return fmt.Errorf("invalid raw TDX Quote")
	}
	return nil
}

// Decode accepts one schema-checked document. Unknown fields or concatenated
// JSON values must not be silently interpreted differently by other components.
func Decode(data []byte, out any) error {
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if err := d.Decode(out); err != nil {
		return err
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}

func ReportDataHex(d RuntimeData) (string, error) {
	b, err := d.ReportData()
	return hex.EncodeToString(b[:]), err
}

// LogEvent writes a structured operational event to stderr, never the plugin RPC
// stream. Events aid diagnostics; Quote/EAR verification remains the authority.
func LogEvent(name string, t Target, details map[string]string) {
	entry := make(map[string]string, len(details)+8)
	for key, value := range details {
		entry[key] = value
	}
	for key, value := range map[string]string{
		"@level": "info", "@message": name, "@timestamp": time.Now().UTC().Format("2006-01-02T15:04:05.000000Z07:00"),
		"event_version": "1", "event": name, "launch_id": t.LaunchID,
		"container_id": t.ContainerID, "pid": t.PID, "start_time": t.StartTime,
		"policy": t.PolicyID,
	} {
		entry[key] = value
	}
	_ = json.NewEncoder(os.Stderr).Encode(entry)
}
