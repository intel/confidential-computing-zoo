package sidecar

import (
	"bytes"
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/jwtbundle"
	"github.com/spiffe/go-spiffe/v2/svid/jwtsvid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/spiffe/spiffe-helper/pkg/disk"
	"github.com/spiffe/spiffe-helper/pkg/util"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"k8s.io/apimachinery/pkg/util/wait"
	"k8s.io/client-go/util/retry"
)

var (
	pidBackoff = wait.Backoff{
		Steps:    10,
		Duration: 100 * time.Millisecond,
		Factor:   2.0,
		Jitter:   0.1,
	}
)

// Event hooks used by unit tests to coordinate goroutines
type hooks struct {
	certReady        func(svids *workloadapi.X509Context)
	cmdExit          func(os.ProcessState)
	pidFileSignalled func(pid int, err error)
}

// Sidecar is the component that consumes the Workload API and renews certs
type Sidecar struct {
	config         *Config
	client         *workloadapi.Client
	jwtSource      *workloadapi.JWTSource
	processRunning bool
	process        *os.Process

	// Mutex to protect processRunning
	mu sync.Mutex

	// Health server
	health Health

	// stdio to connect to the 'cmd' to run. These are used in tests to
	// capture and/or redirect I/O from the guest command. In future they
	// could also be exposed via Config to allow a user of this package to
	// redirect I/O in custom sidecars. These have the same semantics as
	// https://pkg.go.dev/os/exec#Cmd
	stdin  io.Reader
	stdout io.Writer
	stderr io.Writer

	// Used for synchronization in unit tests
	hooks hooks
}

type Health struct {
	FileWriteStatuses FileWriteStatuses `json:"file_write_statuses"`
}

type FileWriteStatuses struct {
	X509WriteStatus *string           `json:"x509_write_status,omitempty"`
	JWTWriteStatus  map[string]string `json:"jwt_write_status"`
}

const (
	writeStatusUnwritten = "unwritten"
	writeStatusFailed    = "failed"
	writeStatusWritten   = "written"
)

// New creates a new SPIFFE sidecar
func New(config *Config) *Sidecar {
	s := &Sidecar{
		config: config,
		health: Health{
			FileWriteStatuses: FileWriteStatuses{
				JWTWriteStatus: make(map[string]string),
			},
		},
		// There's currently no support for controlling stdio
		// redirection in the spiffe-helper configuration or API, these
		// are just used in tests that construct Sidecar directly. In
		// regular use they're always passing through the OS's stdio.
		stdin:  os.Stdin,
		stdout: os.Stdout,
		stderr: os.Stderr,

		// Initialize hooks with noop functions
		hooks: hooks{
			certReady:        func(*workloadapi.X509Context) {},
			cmdExit:          func(os.ProcessState) {},
			pidFileSignalled: func(int, error) {},
		},
	}

	s.setupHealth()
	return s
}

func (s *Sidecar) setupHealth() {
	if s.x509Enabled() {
		writeStatus := writeStatusUnwritten
		s.health.FileWriteStatuses.X509WriteStatus = &writeStatus
	}
	if s.jwtBundleEnabled() {
		jwtBundleFilePath := path.Join(s.config.CertDir, s.config.JWTBundleFilename)
		s.health.FileWriteStatuses.JWTWriteStatus[jwtBundleFilePath] = writeStatusUnwritten
	}
	for _, jwtConfig := range s.config.JWTSVIDs {
		jwtSVIDFilename := path.Join(s.config.CertDir, jwtConfig.JWTSVIDFilename)
		s.health.FileWriteStatuses.JWTWriteStatus[jwtSVIDFilename] = writeStatusUnwritten
	}
}

// RunDaemon starts the main loop
// Starts the workload API client to listen for new SVID updates
// When a new SVID is received on the updateChan, the SVID certificates
// are stored in disk and a restart signal is sent to the proxy's process
func (s *Sidecar) RunDaemon(ctx context.Context) error {
	if err := s.setupClients(ctx); err != nil {
		return err
	}
	if s.client != nil {
		defer s.client.Close()
	}
	if s.jwtSource != nil {
		defer s.jwtSource.Close()
	}

	var tasks []func(context.Context) error

	if s.x509Enabled() {
		s.config.Log.Info("Watching for X509 Context")
		tasks = append(tasks, s.watchX509Context)
	}

	if s.jwtBundleEnabled() {
		s.config.Log.Info("Watching for JWT Bundles")
		tasks = append(tasks, s.watchJWTBundles)
	}

	if s.jwtSVIDsEnabled() {
		tasks = append(tasks, s.watchJWTSVIDs)
	}

	err := util.RunTasks(ctx, tasks...)
	if errors.Is(err, context.Canceled) {
		return nil
	}

	return err
}

func (s *Sidecar) Run(ctx context.Context) error {
	if err := s.setupClients(ctx); err != nil {
		return err
	}
	if s.client != nil {
		defer s.client.Close()
	}
	if s.jwtSource != nil {
		defer s.jwtSource.Close()
	}

	if s.x509Enabled() {
		s.config.Log.Debug("Fetching x509 certificates")
		if err := s.fetchAndWriteX509Context(ctx); err != nil {
			s.config.Log.WithError(err).Error("Error fetching x509 certificates")
			return err
		}
		s.config.Log.Info("Successfully fetched x509 certificates")
	}

	if s.jwtBundleEnabled() {
		s.config.Log.Debug("Fetching JWT Bundle")
		if err := s.fetchAndWriteJWTBundle(ctx); err != nil {
			s.config.Log.WithError(err).Error("Error fetching JWT bundle")
			return err
		}
		s.config.Log.Info("Successfully fetched JWT bundle")
	}

	if s.jwtSVIDsEnabled() {
		s.config.Log.Debug("Fetching JWT SVIDs")
		if err := s.fetchAndWriteJWTSVIDs(ctx); err != nil {
			s.config.Log.WithError(err).Error("Error fetching JWT SVIDs")
			return err
		}
		s.config.Log.Info("Successfully fetched JWT SVIDs")
	}

	return nil
}

// setupClients create the necessary workloadapi clients
func (s *Sidecar) setupClients(ctx context.Context) error {
	if s.x509Enabled() || s.jwtBundleEnabled() {
		client, err := workloadapi.New(ctx, s.getWorkloadAPIAddress())
		if err != nil {
			return err
		}
		s.client = client
	}

	if s.jwtSVIDsEnabled() {
		jwtSource, err := workloadapi.NewJWTSource(ctx, workloadapi.WithClientOptions(s.getWorkloadAPIAddress()))
		if err != nil {
			return err
		}
		s.jwtSource = jwtSource
	}

	return nil
}

// updateCertificates Updates the certificates stored in disk and signal the Process to restart
func (s *Sidecar) updateCertificates(svidResponse *workloadapi.X509Context) {
	s.config.Log.Debug("Updating X.509 certificates")
	if err := disk.WriteX509Context(svidResponse, s.config.AddIntermediatesToBundle, s.config.IncludeFederatedDomains, s.config.OmitExpired, s.config.CertDir, s.config.SVIDFilename, s.config.SVIDKeyFilename, s.config.SVIDBundleFilename, s.config.CertFileMode, s.config.KeyFileMode, s.config.Hint); err != nil {
		s.config.Log.WithError(err).Error("Unable to dump bundle")
		writeStatus := writeStatusFailed
		s.health.FileWriteStatuses.X509WriteStatus = &writeStatus
		return
	}
	writeStatus := writeStatusWritten
	s.health.FileWriteStatuses.X509WriteStatus = &writeStatus
	s.config.Log.Info("X.509 certificates updated")

	if s.config.Cmd != "" {
		if err := s.signalProcess(); err != nil {
			s.config.Log.WithError(err).Error("Unable to signal process")
		}
	}

	if s.config.PIDFilename != "" {
		if err := s.signalPIDFileWithRetry(); err != nil {
			s.config.Log.WithError(err).Error("Unable to signal PID file")
		}
	}

	// TODO: is ReloadExternalProcess still used?
	if s.config.ReloadExternalProcess != nil {
		if err := s.config.ReloadExternalProcess(); err != nil {
			s.config.Log.WithError(err).Error("Unable to reload external process")
		}
	}

	s.hooks.certReady(svidResponse)
}

// signalProcessCMD sends the renew signal to the process or starts it if its first time
// In normal operation this will be called when the workload API client signals a new SVID;
// it will NOT run as soon as an already-running process exits.
func (s *Sidecar) signalProcess() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.processRunning {
		cmdArgs, err := getCmdArgs(s.config.CmdArgs)
		if err != nil {
			return fmt.Errorf("error parsing cmd arguments: %w", err)
		}

		cmd := exec.Command(s.config.Cmd, cmdArgs...) // #nosec

		// By attaching stdin we allow spiffe-helper to be used in a
		// pipeline or as a simple passthrough. Because it consumes the
		// child process's exit status and restarts the child process
		// next time it is signalled it can't be use as a transparent
		// wrapper, but this way we can still send data to the child
		// process.
		//
		// A future enhancement to Run() to launch a child process and
		// wait for it to complete, then exit with the child process's
		// exit code would then allow proper use as a wrapper.
		//
		// If the caller doesn't want it attached, they can close stdin
		// before forking spiffe-helper, same as stdout and stderr.
		cmd.Stdin = s.stdin
		cmd.Stdout = s.stdout
		cmd.Stderr = s.stderr
		if err := cmd.Start(); err != nil {
			return fmt.Errorf("error executing process \"%v\": %w", s.config.Cmd, err)
		}
		s.process = cmd.Process
		s.processRunning = true
		go s.checkProcessExit()
	} else {
		if err := SignalProcess(s.process, s.config.RenewSignal); err != nil {
			return err
		}
	}

	return nil
}

// signalPIDFileWithRetry sends the renew signal to the PID file retrying on error
func (s *Sidecar) signalPIDFileWithRetry() error {
	var pid int
	err := retry.OnError(pidBackoff, func(err error) bool {
		return err != nil
	}, func() (err error) {
		pid, err = s.signalPIDFile()
		return err
	})

	s.hooks.pidFileSignalled(pid, err)
	return err
}

// signalPID sends the renew signal to the PID file
func (s *Sidecar) signalPIDFile() (int, error) {
	fileBytes, err := os.ReadFile(s.config.PIDFilename)
	if err != nil {
		return 0, fmt.Errorf("failed to read pid file %q: %w", s.config.PIDFilename, err)
	}

	pid, err := strconv.Atoi(string(bytes.TrimSpace(fileBytes)))
	if err != nil {
		return 0, fmt.Errorf("failed to parse pid file %q: %w", s.config.PIDFilename, err)
	}

	pidProcess, err := os.FindProcess(pid)
	if err != nil {
		return pid, fmt.Errorf("failed to find process id %d: %w", pid, err)
	}

	return pid, SignalProcess(pidProcess, s.config.RenewSignal)
}

// Goroutine to watch a running process until it exits and report its exit status.
// Does NOT trigger a restart of a process when it exits.
func (s *Sidecar) checkProcessExit() {
	s.mu.Lock()
	if !s.processRunning {
		// This is the only function that should clear the processRunning flag
		// and the routine should only be launched once, when a process has been
		// started.
		panic("checkProcessExit called with no process running")
	}
	// copy the Process object so we don't have to hold the lock while waiting;
	// that would deadlock with signalProcess when there's a workload update.
	proc := s.process
	s.mu.Unlock()

	state, err := proc.Wait()
	if err != nil {
		// We assume the process has exited here, but this could
		// potentially be due to an error in the Wait call. We could
		// look up the process by pid to see if it still exists, but
		// that introduces a pid re-use wait condition. For now,
		// assume that the process has exited.
		s.config.Log.Errorf("error waiting for process exit: %v", err)
	}

	s.hooks.cmdExit(*state)

	s.mu.Lock()
	s.processRunning = false
	s.mu.Unlock()
}

func (s *Sidecar) fetchJWTSVIDs(ctx context.Context, jwtAudience string, jwtExtraAudiences []string) ([]*jwtsvid.SVID, error) {
	jwtSVIDs, err := s.jwtSource.FetchJWTSVIDs(ctx, jwtsvid.Params{Audience: jwtAudience, ExtraAudiences: jwtExtraAudiences})
	if err != nil {
		s.config.Log.Errorf("Unable to fetch JWT SVID: %v", err)
		return nil, err
	}
	for _, jwtSVID := range jwtSVIDs {
		_, err = jwtsvid.ParseAndValidate(jwtSVID.Marshal(), s.jwtSource, []string{jwtAudience})
		if err != nil {
			s.config.Log.Errorf("Unable to parse or validate token: %v", err)
			return nil, err
		}
	}

	return jwtSVIDs, nil
}

func createRetryIntervalFunc() func() time.Duration {
	const (
		initialBackoff = 1 * time.Second
		maxBackoff     = 60 * time.Second
		multiplier     = 2
	)
	backoffInterval := initialBackoff
	return func() time.Duration {
		currentBackoff := backoffInterval
		// Update backoffInterval for next call, capped at maxBackoff
		backoffInterval *= multiplier
		if backoffInterval > maxBackoff {
			backoffInterval = maxBackoff
		}
		return currentBackoff
	}
}

func getRefreshInterval(svid *jwtsvid.SVID) time.Duration {
	return time.Until(svid.Expiry)/2 + time.Second
}

func (s *Sidecar) performJWTSVIDUpdate(ctx context.Context, jwtAudience string, jwtExtraAudiences []string, jwtSVIDFilename string) ([]*jwtsvid.SVID, error) {
	s.config.Log.Debug("Updating JWT SVID")

	jwtSVIDs, err := s.fetchJWTSVIDs(ctx, jwtAudience, jwtExtraAudiences)
	if err != nil {
		s.config.Log.Errorf("Unable to update JWT SVID: %v", err)
		return nil, err
	}

	jwtSVIDPath := path.Join(s.config.CertDir, jwtSVIDFilename)
	if err = disk.WriteJWTSVID(jwtSVIDs, s.config.CertDir, jwtSVIDFilename, s.config.JWTSVIDFileMode, s.config.Hint); err != nil {
		s.config.Log.Errorf("Unable to update JWT SVID: %v", err)
		s.health.FileWriteStatuses.JWTWriteStatus[jwtSVIDPath] = writeStatusFailed
		return nil, err
	}
	s.health.FileWriteStatuses.JWTWriteStatus[jwtSVIDPath] = writeStatusWritten

	s.config.Log.Info("JWT SVID updated")
	return jwtSVIDs, nil
}

func (s *Sidecar) updateJWTSVID(ctx context.Context, jwtAudience string, jwtExtraAudiences []string, jwtSVIDFilename string) {
	retryInterval := createRetryIntervalFunc()
	var initialInterval time.Duration
	jwtSVIDs, err := s.performJWTSVIDUpdate(ctx, jwtAudience, jwtExtraAudiences, jwtSVIDFilename)
	if err != nil {
		// If the first update fails, use the retry interval
		initialInterval = retryInterval()
	} else {
		// If the update succeeds, use the refresh interval
		initialInterval = getRefreshInterval(jwtSVIDs[0])
	}
	ticker := time.NewTicker(initialInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			jwtSVIDs, err = s.performJWTSVIDUpdate(ctx, jwtAudience, jwtExtraAudiences, jwtSVIDFilename)
			if err == nil {
				retryInterval = createRetryIntervalFunc()
				ticker.Reset(getRefreshInterval(jwtSVIDs[0]))
			} else {
				ticker.Reset(retryInterval())
			}
		}
	}
}

func (s *Sidecar) x509Enabled() bool {
	return s.config.SVIDFilename != "" && s.config.SVIDKeyFilename != "" && s.config.SVIDBundleFilename != ""
}

func (s *Sidecar) jwtBundleEnabled() bool {
	return s.config.JWTBundleFilename != ""
}

func (s *Sidecar) jwtSVIDsEnabled() bool {
	return len(s.config.JWTSVIDs) > 0
}

// x509Watcher is a sample implementation of the workload.X509SVIDWatcher interface
type x509Watcher struct {
	sidecar *Sidecar
}

// OnX509ContextUpdate is run every time an SVID is updated
func (w x509Watcher) OnX509ContextUpdate(svids *workloadapi.X509Context) {
	for _, svid := range svids.SVIDs {
		w.sidecar.config.Log.WithField("spiffe_id", svid.ID).Info("Received update")
	}

	w.sidecar.updateCertificates(svids)
}

// OnX509ContextWatchError is run when the client runs into an error
func (w x509Watcher) OnX509ContextWatchError(err error) {
	if status.Code(err) != codes.Canceled {
		w.sidecar.config.Log.Errorf("Error while watching x509 context: %v", err)
	}
}

// getCmdArgs receives the command line arguments as a string
// and split it at spaces, except when the space is inside quotation marks
func getCmdArgs(args string) ([]string, error) {
	if args == "" {
		return []string{}, nil
	}

	r := csv.NewReader(strings.NewReader(args))
	r.Comma = ' ' // space
	cmdArgs, err := r.Read()
	if err != nil {
		return nil, err
	}

	return cmdArgs, nil
}

// JWTBundlesWatcher is an implementation of workload.JWTBundleWatcher interface
type JWTBundlesWatcher struct {
	sidecar *Sidecar
}

// OnJWTBundlesUpdate is run every time a bundle is updated
func (w JWTBundlesWatcher) OnJWTBundlesUpdate(jwkSet *jwtbundle.Set) {
	w.sidecar.config.Log.Debug("Updating JWT bundle")
	jwtBundleFilePath := path.Join(w.sidecar.config.CertDir, w.sidecar.config.JWTBundleFilename)
	if err := disk.WriteJWTBundleSet(jwkSet, w.sidecar.config.CertDir, w.sidecar.config.JWTBundleFilename, w.sidecar.config.JWTBundleFileMode); err != nil {
		w.sidecar.config.Log.Errorf("Error writing JWT Bundle to disk: %v", err)
		w.sidecar.health.FileWriteStatuses.JWTWriteStatus[jwtBundleFilePath] = writeStatusFailed
		return
	}
	w.sidecar.health.FileWriteStatuses.JWTWriteStatus[jwtBundleFilePath] = writeStatusWritten

	w.sidecar.config.Log.Info("JWT bundle updated")
}

// OnJWTBundlesWatchError is run when the client runs into an error
func (w JWTBundlesWatcher) OnJWTBundlesWatchError(err error) {
	if status.Code(err) != codes.Canceled {
		w.sidecar.config.Log.Errorf("Error while watching JWT bundles: %v", err)
	}
}

func (s *Sidecar) CheckLiveness() bool {
	for _, writeStatus := range s.health.FileWriteStatuses.JWTWriteStatus {
		if writeStatus == writeStatusFailed {
			return false
		}
	}
	if s.x509Enabled() && *s.health.FileWriteStatuses.X509WriteStatus == writeStatusFailed {
		return false
	}
	return true
}

func (s *Sidecar) CheckReadiness() bool {
	for _, writeStatus := range s.health.FileWriteStatuses.JWTWriteStatus {
		if writeStatus != writeStatusWritten {
			return false
		}
	}
	return !s.x509Enabled() || *s.health.FileWriteStatuses.X509WriteStatus == writeStatusWritten
}

func (s *Sidecar) GetHealth() Health {
	return s.health
}
