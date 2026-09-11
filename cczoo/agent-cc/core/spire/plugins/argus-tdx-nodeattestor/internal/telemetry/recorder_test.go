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

package telemetry

import (
	"context"
	"fmt"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestResultReasonsAreStable(t *testing.T) {
	tests := []struct {
		name    string
		result  string
		reason  string
		err     error
		trustee bool
	}{
		{name: "success", result: "success", reason: "ok"},
		{name: "permission", result: "error", reason: "permission_denied", err: status.Error(codes.PermissionDenied, "denied")},
		{name: "trustee HTTP", result: "error", reason: "http_503", err: fmt.Errorf("Trustee returned HTTP 503"), trustee: true},
		{name: "trustee timeout", result: "error", reason: "deadline_exceeded", err: fmt.Errorf("verify: %w", context.DeadlineExceeded), trustee: true},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var result, reason string
			if test.trustee {
				result, reason = trusteeResultAndReason(test.err)
			} else {
				result, reason = resultAndReason(test.err)
			}
			if result != test.result || reason != test.reason {
				t.Fatalf("result/reason = %q/%q, want %q/%q", result, reason, test.result, test.reason)
			}
		})
	}
}
