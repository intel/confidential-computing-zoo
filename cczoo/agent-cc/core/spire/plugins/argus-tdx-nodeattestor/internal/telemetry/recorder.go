// Package telemetry reports bounded NodeAttestor metrics through SPIRE host
// services without changing the attestation result.
package telemetry

import (
	"context"
	"errors"
	"strings"
	"time"
	"unicode"

	"github.com/spiffe/spire-plugin-sdk/pluginsdk"
	metricsapi "github.com/spiffe/spire-plugin-sdk/proto/spire/hostservice/common/metrics/v1"
	"google.golang.org/grpc/status"
)

// Recorder emits best-effort SPIRE host metrics. Metrics failures never alter
// the attestation decision or mask the original protocol error.
type Recorder struct {
	client metricsapi.MetricsServiceClient
}

// Broker connects the recorder to SPIRE's metrics host service.
func (recorder *Recorder) Broker(broker pluginsdk.ServiceBroker) {
	broker.BrokerClient(&recorder.client)
}

// Attestation records one Agent-side protocol result and duration.
func (recorder *Recorder) Attestation(side string, started time.Time, err error) {
	result, reason := resultAndReason(err)
	recorder.increment([]string{"argus_nodeattestor", "attempts"}, labels(
		"side", side, "result", result, "reason", reason,
	))
	if !recorder.client.IsInitialized() {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_, _ = recorder.client.MeasureSince(ctx, &metricsapi.MeasureSinceRequest{
		Key: []string{"argus_nodeattestor", "duration"}, Time: started.UnixNano(),
		Labels: labels("side", side),
	})
}

// EvidenceBytes records the raw Quote size returned by the Provider.
func (recorder *Recorder) EvidenceBytes(side string, size int) {
	if !recorder.client.IsInitialized() || size < 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_, _ = recorder.client.AddSample(ctx, &metricsapi.AddSampleRequest{
		Key: []string{"argus_nodeattestor", "evidence_bytes"}, Val: float32(size),
		Labels: labels("side", side),
	})
}

// Trustee records a bounded classification for one appraisal request.
func (recorder *Recorder) Trustee(err error) {
	result, reason := trusteeResultAndReason(err)
	recorder.increment([]string{"argus_nodeattestor", "trustee_requests"}, labels(
		"result", result, "reason", reason,
	))
}

func (recorder *Recorder) increment(key []string, metricLabels []*metricsapi.Label) {
	if !recorder.client.IsInitialized() {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	_, _ = recorder.client.IncrCounter(ctx, &metricsapi.IncrCounterRequest{
		Key: key, Val: 1, Labels: metricLabels,
	})
}

func resultAndReason(err error) (string, string) {
	if err == nil {
		return "success", "ok"
	}
	return "error", snakeCase(status.Code(err).String())
}

func trusteeResultAndReason(err error) (string, string) {
	if err == nil {
		return "success", "ok"
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "error", "deadline_exceeded"
	}
	// Keep labels bounded and stable instead of exporting full error strings.
	const marker = "Trustee returned HTTP "
	if index := strings.Index(err.Error(), marker); index >= 0 {
		statusCode := strings.Fields(err.Error()[index+len(marker):])
		if len(statusCode) > 0 {
			return "error", "http_" + statusCode[0]
		}
	}
	return "error", "unknown"
}

func snakeCase(input string) string {
	var output strings.Builder
	for index, character := range input {
		if unicode.IsUpper(character) {
			if index > 0 {
				output.WriteByte('_')
			}
			character = unicode.ToLower(character)
		}
		output.WriteRune(character)
	}
	return output.String()
}

func labels(values ...string) []*metricsapi.Label {
	output := make([]*metricsapi.Label, 0, len(values)/2)
	for index := 0; index+1 < len(values); index += 2 {
		output = append(output, &metricsapi.Label{Name: values[index], Value: values[index+1]})
	}
	return output
}
