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

package workloadattestor

import (
	"context"
	"crypto/ecdsa"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-workloadattestor/internal/evidence"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-workloadattestor/internal/protocol"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/plugins/argus-tdx-workloadattestor/internal/trustee"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/target"
	"github.com/spiffe/go-spiffe/v2/exp/proto/spiffe/broker"
	workloadattestorv1 "github.com/spiffe/spire-plugin-sdk/proto/spire/plugin/agent/workloadattestor/v1"
	configv1 "github.com/spiffe/spire-plugin-sdk/proto/spire/service/common/config/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/anypb"
)

const workloadPIDReferenceTypeURL = "type.googleapis.com/spiffe.broker.WorkloadPIDReference"

type EvidenceCollector interface {
	Collect(context.Context, protocol.EvidenceRequest) (protocol.Evidence, error)
}
type TrusteeVerifier interface {
	Verify(context.Context, protocol.Evidence) error
}
type Plugin struct {
	workloadattestorv1.UnimplementedWorkloadAttestorServer
	configv1.UnimplementedConfigServer
	clientsMu sync.RWMutex
	evidence  EvidenceCollector
	trustee   TrusteeVerifier
	config    *Config
	nonce     func() (string, error)
	load      func(string) (protocol.Target, error)
	check     func(protocol.Target) error
}

func New(e EvidenceCollector, t TrusteeVerifier) *Plugin {
	return &Plugin{evidence: e, trustee: t, nonce: newNonce, load: target.Load, check: target.Check}
}

// Ordinary Workload API callers cannot obtain the remote-attestation selectors.
func (p *Plugin) Attest(context.Context, *workloadattestorv1.AttestRequest) (*workloadattestorv1.AttestResponse, error) {
	return &workloadattestorv1.AttestResponse{}, nil
}

// AttestReference appraises one registered PID instance for a Broker request.
// Local instance checks bracket appraisal; they do not lock the process or
// establish continuous integrity after this call returns.
func (p *Plugin) AttestReference(ctx context.Context, r *workloadattestorv1.AttestReferenceRequest) (*workloadattestorv1.AttestReferenceResponse, error) {
	// Use one coherent client/config snapshot if Configure runs concurrently.
	// Appraisal can then proceed without holding the configuration lock.
	p.clientsMu.RLock()
	ec, tc, c := p.evidence, p.trustee, p.config
	p.clientsMu.RUnlock()
	if ec == nil || tc == nil || c == nil {
		return nil, status.Error(codes.FailedPrecondition, "plugin is not configured")
	}
	ref := r.GetReference()
	// The Broker's reference identifies the workload PID, not the Helper's PID.
	// Ordinary Workload API callers take the separate Attest path above.
	if ref.GetTypeUrl() != workloadPIDReferenceTypeURL {
		return nil, status.Error(codes.InvalidArgument, "unsupported workload reference")
	}
	var pid broker.WorkloadPIDReference
	if err := anypb.UnmarshalTo(ref, &pid, proto.UnmarshalOptions{}); err != nil || pid.Pid <= 0 {
		return nil, status.Error(codes.InvalidArgument, "invalid workload PID")
	}
	nonce, err := p.nonce()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "nonce: %v", err)
	}
	t, err := p.load(c.TargetRegistrationPath)
	if err != nil {
		return nil, status.Errorf(codes.FailedPrecondition, "load target: %v", err)
	}
	if err = c.checkApproved(t); err != nil {
		return nil, status.Error(codes.PermissionDenied, err.Error())
	}
	if t.PID != strconv.FormatInt(int64(pid.Pid), 10) {
		return nil, status.Error(codes.PermissionDenied, "PID is not the registered instance")
	}
	if err = p.check(t); err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "target changed: %v", err)
	}
	req := protocol.EvidenceRequest{Protocol: protocol.Name, Nonce: nonce, PID: pid.Pid}
	ev, err := ec.Collect(ctx, req)
	if err != nil {
		return nil, status.Errorf(codes.Unavailable, "collect evidence: %v", err)
	}
	if err = ev.Validate(req, t); err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "evidence binding: %v", err)
	}
	if err = tc.Verify(ctx, ev); err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "Trustee appraisal: %v", err)
	}
	err = p.check(t)
	if err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "target changed during appraisal: %v", err)
	}
	// These values come from the approved target matched to the Quote-bound
	// runtime data and signed EAR. SPIRE adds the plugin selector type; its
	// Server CA issues the SVID after registration matching.
	return &workloadattestorv1.AttestReferenceResponse{SelectorValues: []string{
		"verified:true", "workload_id:" + t.WorkloadID, "policy:" + t.PolicyID,
		"image_config_digest:" + t.ImageConfigDigest, "config_digest:" + t.ConfigDigest,
		"agent_id:" + t.AgentID,
	}}, nil
}
func (p *Plugin) Validate(_ context.Context, r *configv1.ValidateRequest) (*configv1.ValidateResponse, error) {
	_, notes := parseConfig(r.GetHclConfiguration())
	return &configv1.ValidateResponse{Valid: len(notes) == 0, Notes: notes}, nil
}
func (p *Plugin) Configure(_ context.Context, r *configv1.ConfigureRequest) (*configv1.ConfigureResponse, error) {
	c, notes := parseConfig(r.GetHclConfiguration())
	if len(notes) > 0 {
		return nil, status.Error(codes.InvalidArgument, strings.Join(notes, "; "))
	}
	tlsConfig, key, err := loadTrust(c)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "Trustee trust: %v", err)
	}
	ec, err := evidence.NewClient(c.EvidenceEndpoint, c.RequestTimeout, c.MaxResponseBytes)
	if err != nil {
		return nil, err
	}
	tc, err := trustee.NewClient(c.TrusteeEndpoint, tlsConfig, key, c.EARExpectedIssuer, c.EARExpectedProfile, c.PolicyID, c.RequestTimeout, c.MaxResponseBytes)
	if err != nil {
		return nil, err
	}
	// Publish the new trust settings and both clients together only after all
	// configuration and trust-material checks have succeeded.
	p.clientsMu.Lock()
	p.evidence, p.trustee, p.config = ec, tc, c
	p.clientsMu.Unlock()
	return &configv1.ConfigureResponse{}, nil
}
func loadTrust(c *Config) (*tls.Config, *ecdsa.PublicKey, error) {
	b, err := os.ReadFile(c.TrusteeCAPath)
	if err != nil {
		return nil, nil, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(b) {
		return nil, nil, fmt.Errorf("empty Trustee CA")
	}
	b, err = os.ReadFile(c.EARPublicKeyPath)
	if err != nil {
		return nil, nil, err
	}
	block, rest := pem.Decode(b)
	if block == nil || block.Type != "PUBLIC KEY" || strings.TrimSpace(string(rest)) != "" {
		return nil, nil, fmt.Errorf("EAR key must contain one PKIX PUBLIC KEY")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, nil, err
	}
	key, ok := pub.(*ecdsa.PublicKey)
	if !ok {
		return nil, nil, fmt.Errorf("EAR key must be ECDSA")
	}
	return &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots, ServerName: c.TrusteeServerName}, key, nil
}
func newNonce() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
