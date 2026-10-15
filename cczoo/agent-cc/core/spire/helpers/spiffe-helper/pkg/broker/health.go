package broker

import (
	"context"
	"fmt"
	"sync"
	"time"
)

const (
	progressMaxAge = 2 * time.Second
	hookTimeout    = 5 * time.Second
	hookWaitDelay  = time.Second
)

// health observes completed work, not the liveness of a timer goroutine. Long
// initialization/publication has an explicit, non-renewable deadline. Nothing
// here subscribes to the Broker or collects new attestation evidence.
type health struct {
	mu             sync.Mutex
	checked        time.Time
	progress       time.Time
	operation      time.Time
	operationName  string
	initializing   bool
	startup        time.Time
	credentialEnds time.Time
}

func newHealth(now time.Time, startup time.Duration) *health {
	return &health{initializing: true, startup: now.Add(startup)}
}

func (h *health) targetChecked(now time.Time) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.checked = now
}

func (h *health) loopProgress(now time.Time) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.progress = now
}

func (h *health) publishing(now, expires time.Time) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.operationName = "credential publication"
	h.operation = now.Add(hookTimeout + hookWaitDelay)
	if expires.Before(h.operation) {
		h.operation = expires
	}
}

func (h *health) published(now, expires time.Time) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.initializing = false
	h.operation = time.Time{}
	h.operationName = ""
	h.progress = now
	h.credentialEnds = expires
}

func (h *health) check(now time.Time) error {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.checked.IsZero() || now.Sub(h.checked) > progressMaxAge {
		return fmt.Errorf("target check progress expired")
	}
	if !h.credentialEnds.IsZero() && !now.Before(h.credentialEnds) {
		return fmt.Errorf("published target credentials expired")
	}
	if h.initializing && !now.Before(h.startup) {
		return fmt.Errorf("credential initialization progress expired")
	}
	if !h.operation.IsZero() {
		// Publication may temporarily pause the consumer loop, but its fixed
		// budget never bypasses target-check freshness or credential expiry above.
		if !now.Before(h.operation) {
			return fmt.Errorf("%s progress expired", h.operationName)
		}
		return nil
	}
	if !h.initializing && (h.progress.IsZero() || now.Sub(h.progress) > progressMaxAge) {
		return fmt.Errorf("credential consumer progress expired")
	}
	return nil
}

// runHealth also enforces progress when the Helper is run outside systemd. A
// systemd watchdog additionally covers SIGSTOP, process death and stuck cleanup.
func runHealth(ctx context.Context, h *health, interval time.Duration, notify func() error, failed func(error)) {
	tick := time.NewTicker(interval)
	defer tick.Stop()
	for {
		if ctx.Err() != nil {
			return
		}
		if err := h.check(time.Now()); err != nil {
			failed(err)
			return
		}
		if notify != nil {
			if err := notify(); err != nil {
				failed(fmt.Errorf("systemd watchdog notification: %w", err))
				return
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
		}
	}
}
