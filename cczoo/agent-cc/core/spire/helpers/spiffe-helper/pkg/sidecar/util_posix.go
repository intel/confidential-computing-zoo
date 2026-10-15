//go:build !windows
// +build !windows

package sidecar

import (
	"fmt"
	"os"

	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"golang.org/x/sys/unix"
)

func (s *Sidecar) getWorkloadAPIAddress() workloadapi.ClientOption {
	return workloadapi.WithAddr("unix://" + s.config.AgentAddress)
}

func SignalProcess(process *os.Process, renewSignal string) error {
	if renewSignal == "" {
		return nil
	}
	sig := unix.SignalNum(renewSignal)
	if sig == 0 {
		return fmt.Errorf("error getting signal: %v", renewSignal)
	}

	if err := process.Signal(sig); err != nil {
		return fmt.Errorf("error signaling process with signal num %v: %w", sig, err)
	}

	return nil
}
