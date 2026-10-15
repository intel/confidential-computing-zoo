package health

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	"github.com/spiffe/spiffe-helper/pkg/sidecar"
)

type Config struct {
	ListenerEnabled bool   `hcl:"listener_enabled"`
	BindPort        int    `hcl:"bind_port"`
	LivenessPath    string `hcl:"liveness_path"`
	ReadinessPath   string `hcl:"readiness_path"`
}

const (
	contentTypeJSON          = "application/json"
	contentTypePlainText     = "text/plain"
	statusOK                 = http.StatusOK
	statusServiceUnavailable = http.StatusServiceUnavailable
)

type Health struct {
	c       *Config
	log     logrus.FieldLogger
	sidecar *sidecar.Sidecar
}

func New(config *Config, log logrus.FieldLogger, sidecar *sidecar.Sidecar) *Health {
	return &Health{
		c:       config,
		log:     log,
		sidecar: sidecar,
	}
}

func (h *Health) Start(ctx context.Context) error {
	h.log.Info("Starting health server")
	http.HandleFunc(h.c.LivenessPath, func(w http.ResponseWriter, _ *http.Request) {
		writeResponse(w, h.sidecar.CheckLiveness(), h.log, h.sidecar)
	})
	http.HandleFunc(h.c.ReadinessPath, func(w http.ResponseWriter, _ *http.Request) {
		writeResponse(w, h.sidecar.CheckReadiness(), h.log, h.sidecar)
	})
	server := &http.Server{
		Addr:              ":" + strconv.Itoa(h.c.BindPort),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      5 * time.Second,
	}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		err := server.ListenAndServe()
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			h.log.WithError(err).Warn("Error serving health checks")
		}
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		<-ctx.Done()
		_ = server.Close()
	}()

	wg.Wait()

	return ctx.Err()
}

type Response struct {
	Status string         `json:"status"`
	Health sidecar.Health `json:"health"`
}

func writeResponse(w http.ResponseWriter, goodStatus bool, log logrus.FieldLogger, sidecar *sidecar.Sidecar) {
	statusCode := statusOK
	statusText := http.StatusText(statusOK)

	if !goodStatus {
		statusCode = statusServiceUnavailable
		statusText = http.StatusText(statusServiceUnavailable)
	}

	response := Response{
		Status: statusText,
		Health: sidecar.GetHealth(),
	}

	jsonBytes, err := json.Marshal(response)
	if err != nil {
		log.WithError(err).Errorf("failed marshalling response")
		w.Header().Set("Content-Type", contentTypePlainText)
		w.WriteHeader(statusCode)
		_, err = w.Write([]byte(statusText))
		if err != nil {
			log.WithError(err).Errorf("failed writing response text")
		}
		return
	}

	w.Header().Set("Content-Type", contentTypeJSON)
	w.WriteHeader(statusCode)
	_, err = w.Write(jsonBytes)
	if err != nil {
		log.WithError(err).Errorf("failed writing response JSON")
	}
}
