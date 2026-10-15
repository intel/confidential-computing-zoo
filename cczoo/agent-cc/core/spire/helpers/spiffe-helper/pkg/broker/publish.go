package broker

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
)

// Publisher requires serialized use of its private directory. Each generation
// contains all three PEM files before current switches. The deployment hook
// validates NGINX configuration and loaded certificate before ready is published;
// it does not perform business authorization or an application-level request.
type Publisher struct {
	Dir          string
	Hook         func(context.Context, string) error
	checkFS      func(string) error
	InvocationID string
	Target       protocol.Target
}

// Readiness is an atomic snapshot for the current Helper invocation and target.
// It is local operational state, not a replacement for attestation evidence.
type Readiness struct {
	SchemaVersion int             `json:"schema_version"`
	InvocationID  string          `json:"invocation_id"`
	Serial        string          `json:"serial"`
	ExpiresAt     time.Time       `json:"expires_at"`
	Target        protocol.Target `json:"target"`
}

func NewPublisher(dir, hook string) *Publisher {
	return &Publisher{Dir: dir, checkFS: checkTmpfs, Hook: func(ctx context.Context, action string) error {
		ctx, cancel := context.WithTimeout(ctx, hookTimeout)
		defer cancel()
		command := exec.CommandContext(ctx, hook, action)
		// A terminated hook may leave descendants holding its output pipes.
		// Bound pipe draining as well as the lifetime of the direct child.
		command.WaitDelay = hookWaitDelay
		out, err := command.CombinedOutput()
		if err != nil {
			return fmt.Errorf("NGINX %s hook: %w: %s", action, err, out)
		}
		return nil
	}}
}
func (p *Publisher) Prepare() error {
	if err := os.MkdirAll(p.Dir, 0700); err != nil {
		return err
	}
	if err := p.checkFS(p.Dir); err != nil {
		return err
	}
	return p.Clear()
}

// Clear removes this publisher's local files. The caller must also stop NGINX;
// deleting PEM does not erase in-memory keys or revoke issued certificates.
func (p *Publisher) Clear() error {
	entries, err := os.ReadDir(p.Dir)
	if err != nil {
		return err
	}
	var errs []error
	for _, e := range entries {
		if e.Name() == "current" || e.Name() == "ready" || e.Name() == ".ready-next" || e.Name() == ".next" || strings.HasPrefix(e.Name(), "generation-") {
			// Only our direct children are removed; RemoveAll never follows symlinks.
			errs = append(errs, os.RemoveAll(filepath.Join(p.Dir, e.Name())))
		}
	}
	return errors.Join(errs...)
}
func (p *Publisher) Publish(ctx context.Context, c *Credentials) error {
	ctx, cancel := context.WithDeadline(ctx, c.Expires)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("credentials expired before publication: %w", err)
	}
	generation, err := os.MkdirTemp(p.Dir, "generation-")
	if err != nil {
		return err
	}
	published := false
	defer func() {
		if !published {
			_ = os.RemoveAll(generation)
		}
	}()
	for name, data := range map[string][]byte{"svid.pem": c.Certificate, "key.pem": c.Key, "bundle.pem": c.Bundle} {
		if err = os.WriteFile(filepath.Join(generation, name), data, 0600); err != nil {
			return err
		}
	}
	next := filepath.Join(p.Dir, ".next")
	// Complete the private generation before switching current. Run serializes
	// publication and the reload hook, so a reload finishes before another switch.
	if err = os.Symlink(filepath.Base(generation), next); err != nil {
		return err
	}
	if err = os.Rename(next, filepath.Join(p.Dir, "current")); err != nil {
		_ = os.Remove(next)
		return err
	}
	if err = p.Hook(ctx, "publish"); err != nil {
		_ = p.Clear()
		return err
	}
	if err = ctx.Err(); err != nil {
		_ = p.Clear()
		return fmt.Errorf("credentials expired or publication canceled: %w", err)
	}
	readyNext := filepath.Join(p.Dir, ".ready-next")
	// Publish readiness only after the hook confirms that ingress loaded this
	// generation. Invocation/target fields let recovery reject stale ready files.
	ready, err := json.Marshal(Readiness{SchemaVersion: 1, InvocationID: p.InvocationID, Serial: c.Serial, ExpiresAt: c.Expires.UTC(), Target: p.Target})
	if err != nil {
		_ = p.Clear()
		return err
	}
	if err = os.WriteFile(readyNext, append(ready, '\n'), 0600); err != nil {
		_ = p.Clear()
		return err
	}
	if err = os.Rename(readyNext, filepath.Join(p.Dir, "ready")); err != nil {
		_ = p.Clear()
		return err
	}
	published = true
	entries, err := os.ReadDir(p.Dir)
	if err != nil {
		return err
	}
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), "generation-") && e.Name() != filepath.Base(generation) {
			if err = os.RemoveAll(filepath.Join(p.Dir, e.Name())); err != nil {
				return err
			}
		}
	}
	return nil
}
