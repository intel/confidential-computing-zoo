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
