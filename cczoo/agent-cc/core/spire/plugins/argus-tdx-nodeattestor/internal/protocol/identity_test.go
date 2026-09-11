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
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestAgentTrustDomain(t *testing.T) {
	contents, err := os.ReadFile("testdata/agent-identities.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name        string `json:"name"`
		AgentID     string `json:"agent_id"`
		TrustDomain string `json:"trust_domain"`
		Padding     int    `json:"padding"`
	}
	if err := json.Unmarshal(contents, &cases); err != nil {
		t.Fatal(err)
	}
	for _, tc := range cases {
		t.Run(tc.Name, func(t *testing.T) {
			id := tc.AgentID + strings.Repeat("x", tc.Padding)
			domain, err := AgentTrustDomain(id)
			wantValid := tc.TrustDomain != ""
			if (err == nil) != wantValid || domain != tc.TrustDomain {
				t.Fatalf("domain = %q, error = %v, want domain %q", domain, err, tc.TrustDomain)
			}
			if _, err := NodeRuntimeData(id, make([]byte, NonceSize), make([]byte, PublicKeySize)); (err == nil) != wantValid {
				t.Fatalf("runtime data validation disagrees with identity contract: %v", err)
			}
		})
	}
}

func TestReportDataBindsConfiguredIdentity(t *testing.T) {
	nonce, key := make([]byte, NonceSize), make([]byte, PublicKeySize)
	first, err := ReportData(testAgentID, nonce, key)
	if err != nil {
		t.Fatal(err)
	}
	second, err := ReportData("spiffe://example.org/spire/agent/argus_tdx/worker-02", nonce, key)
	if err != nil {
		t.Fatal(err)
	}
	if first == second {
		t.Fatal("changing the configured identity did not change REPORTDATA")
	}
}
