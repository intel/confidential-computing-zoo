package broker

import (
	"context"
	"errors"
	"fmt"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/target"
	api "github.com/spiffe/go-spiffe/v2/exp/proto/spiffe/broker"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/protobuf/types/known/anypb"
	"net"
	"net/url"
	"strconv"
	"time"
)

// Run owns one target subscription and serialized credential publisher. After
// publisher preparation, all exits clear credentials and invoke the stop hook.
func Run(ctx context.Context, agentAddress, certDir string, c Config) (result error) {
	if err := c.Validate(certDir); err != nil {
		return err
	}
	ctx, cancel := context.WithCancelCause(ctx)
	defer cancel(nil)
	p := NewPublisher(certDir, c.PublishHook)
	if err := p.Prepare(); err != nil {
		return err
	}
	defer func() {
		cancel(nil)
		clearErr := p.Clear()
		stopCtx, stop := context.WithTimeout(context.Background(), 5*time.Second)
		defer stop()
		result = errors.Join(result, clearErr, p.Hook(stopCtx, "stop"))
	}()
	w, err := watchdogFromEnvironment()
	if err != nil {
		return err
	}
	t, err := target.Load(c.TargetRegistrationPath)
	if err != nil {
		return err
	}
	if t.AgentID != c.AgentSPIFFEID || t.WorkloadID != c.WorkloadID {
		return fmt.Errorf("registered target identity mismatch")
	}
	startupTimeout, err := c.startupTimeout()
	if err != nil {
		return err
	}
	p.InvocationID, p.Target = w.invocationID, t
	h := newHealth(time.Now(), startupTimeout)
	watchErr, err := target.StartWatchWithProgress(ctx, t, h.targetChecked)
	if err != nil {
		return err
	}
	// With Type=simple, the first completed local check starts heartbeats before
	// potentially slow attestation. A stuck local initialization never feeds it.
	go runHealth(ctx, h, w.interval, w.notify, cancel)
	err = supervise(ctx, watchErr, startupTimeout, func(ctx context.Context, published func()) error {
		return subscribe(ctx, agentAddress, c, t, p, published, h)
	})
	return errors.Join(err, context.Cause(ctx))
}

// Monitor the target while the Workload API and Broker are initializing as well
// as during publication. The startup budget ends only after the first publish.
func supervise(parent context.Context, targetErrors <-chan error, timeout time.Duration, run func(context.Context, func()) error) error {
	ctx, cancel := context.WithCancelCause(parent)
	defer cancel(nil)
	startup := time.AfterFunc(timeout, func() {
		cancel(fmt.Errorf("target credentials unavailable during initialization: %w", context.DeadlineExceeded))
	})
	defer startup.Stop()
	go func() {
		select {
		case <-ctx.Done():
		case err := <-targetErrors:
			if err == nil {
				err = errors.New("target watch ended")
			}
			cancel(fmt.Errorf("target instance ended: %w", err))
		}
	}()
	err := run(ctx, func() { startup.Stop() })
	return errors.Join(context.Cause(ctx), err)
}

func subscribe(ctx context.Context, agentAddress string, c Config, t protocol.Target, p *Publisher, published func(), h *health) error {
	helperID, _ := spiffeid.FromString(c.HelperSPIFFEID)
	agentID, _ := spiffeid.FromString(c.AgentSPIFFEID)
	targetID, _ := spiffeid.FromString(c.TargetSPIFFEID)
	source, err := workloadapi.NewX509Source(ctx, workloadapi.WithClientOptions(workloadapi.WithAddr(agentAddress)), workloadapi.WithDefaultX509SVIDPicker(func(svids []*x509svid.SVID) *x509svid.SVID {
		for _, s := range svids {
			if s.ID == helperID {
				return s
			}
		}
		return nil
	}))
	if err != nil {
		return err
	}
	defer source.Close()
	self, err := source.GetX509SVID()
	if err != nil || self.ID != helperID {
		return fmt.Errorf("Helper identity unavailable")
	}
	ep, _ := url.Parse(c.Endpoint)
	// A local socket is still an authenticated Broker connection: present the
	// Helper SVID and require the exact configured Agent SPIFFE identity.
	conn, err := grpc.NewClient("passthrough:///argus-broker",
		grpc.WithTransportCredentials(credentials.NewTLS(tlsconfig.MTLSClientConfig(source, source, tlsconfig.AuthorizeID(agentID)))),
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", ep.Path)
		}),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(4<<20)))
	if err != nil {
		return err
	}
	defer conn.Close()
	pid, _ := strconv.ParseInt(t.PID, 10, 32)
	// Ask on behalf of the registered server process, rather than obtaining a
	// target identity through the Helper's ordinary Workload API selectors.
	ref, err := anypb.New(&api.WorkloadPIDReference{Pid: int32(pid)})
	if err != nil {
		return err
	}
	// Emit before sending the request so appraisal events follow this boundary.
	protocol.LogEvent("workload.subscription_started", t, map[string]string{"subscription_id": p.InvocationID})
	defer protocol.LogEvent("workload.subscription_ended", t, map[string]string{"subscription_id": p.InvocationID})
	stream, err := api.NewAPIClient(conn).SubscribeToX509SVID(metadata.AppendToOutgoingContext(ctx, "broker.spiffe.io", "true"), &api.SubscribeToX509SVIDRequest{Reference: &api.WorkloadReference{Reference: ref}})
	if err != nil {
		return err
	}
	return consume(ctx, stream.Recv, p, targetID, t, published, func() error {
		s, err := source.GetX509SVID()
		if err != nil {
			return err
		}
		if s.ID != helperID || !time.Now().Before(s.Certificates[0].NotAfter) {
			return fmt.Errorf("Helper identity removed or expired")
		}
		return nil
	}, h)
}

// A disconnect returns to Run's credential cleanup and NGINX stop hook. systemd
// may start a new process, which performs a new PID-reference subscription and
// attestation. SVID updates on this stream alone do not request a fresh Quote.
func consume(ctx context.Context, recv func() (*api.SubscribeToX509SVIDResponse, error), p *Publisher, id spiffeid.ID, t protocol.Target, published func(), checkSelf func() error, monitors ...*health) error {
	var h *health
	if len(monitors) > 0 {
		h = monitors[0]
	}
	type message struct {
		snapshot *api.SubscribeToX509SVIDResponse
		err      error
	}
	updates := make(chan message)
	go func() {
		for {
			r, err := recv()
			select {
			case updates <- message{r, err}:
			case <-ctx.Done():
				return
			}
			if err != nil {
				return
			}
		}
	}()
	tick := time.NewTicker(250 * time.Millisecond)
	defer tick.Stop()
	var deadline time.Time
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-tick.C:
			// Enforce expiry even when the Broker sends no new snapshot. This
			// timer is a local lifetime check and does not re-appraise a Quote.
			if !deadline.IsZero() && !time.Now().Before(deadline) {
				return fmt.Errorf("target credentials unavailable or expired")
			}
			if err := checkSelf(); err != nil {
				return err
			}
			if h != nil {
				h.loopProgress(time.Now())
			}
		case m := <-updates:
			if m.err != nil {
				return fmt.Errorf("Broker subscription ended: %w", m.err)
			}
			c, err := Snapshot(m.snapshot, id, time.Now())
			if err != nil {
				return err
			}
			if h != nil {
				h.publishing(time.Now(), c.Expires)
			}
			if err = p.Publish(ctx, c); err != nil {
				return err
			}
			if h != nil {
				h.published(time.Now(), c.Expires)
			}
			published()
			if err := ctx.Err(); err != nil {
				return err
			}
			deadline = c.Expires
			protocol.LogEvent("workload.svid_published", t, map[string]string{"serial": c.Serial, "expires": c.Expires.UTC().Format(time.RFC3339), "subscription_id": p.InvocationID})
		}
	}
}
