// Copyright (c) 2026 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//go:build linux

package target

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
	"golang.org/x/sys/unix"
)

type containerInfo struct {
	ID    string `json:"Id"`
	Image string
	State struct {
		PID     int `json:"Pid"`
		Running bool
	}
	Config     struct{ Labels map[string]string }
	HostConfig struct {
		ReadonlyRootfs bool
		Privileged     bool
		NetworkMode    string
		PidMode        string
	}
}

func checkOwner(info os.FileInfo) error {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != 0 || info.Mode().Perm()&0022 != 0 {
		return fmt.Errorf("target registration must be root-owned and not writable by group or others")
	}
	return nil
}

func inspect(ctx context.Context, id string) (containerInfo, error) {
	var empty containerInfo
	if len(id) != 64 {
		return empty, fmt.Errorf("full container ID required")
	}
	if _, err := hex.DecodeString(id); err != nil {
		return empty, err
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	b, err := exec.CommandContext(ctx, "docker", "inspect", id).Output()
	if err != nil {
		return empty, fmt.Errorf("docker inspect: %w", err)
	}
	var results []containerInfo
	if err = json.Unmarshal(b, &results); err != nil {
		return empty, err
	}
	if len(results) != 1 || results[0].ID != id || !results[0].State.Running || !protocol.Digest(results[0].Image) {
		return empty, fmt.Errorf("container is not running with an actual image config digest")
	}
	if !results[0].HostConfig.ReadonlyRootfs || results[0].HostConfig.Privileged || results[0].HostConfig.NetworkMode == "host" || results[0].HostConfig.PidMode == "host" {
		return empty, fmt.Errorf("workload container must have read-only rootfs and privileged=false")
	}
	return results[0], nil
}

func procString(pid, name string) (string, error) {
	b, err := os.ReadFile(filepath.Join("/proc", pid, name))
	return strings.TrimSpace(string(b)), err
}
func procLink(pid, name string) (string, error) {
	return os.Readlink(filepath.Join("/proc", pid, name))
}
func startTime(pid string) (string, error) {
	stat, err := procString(pid, "stat")
	if err != nil {
		return "", err
	}
	// The comm field can contain spaces and parentheses; only split fields
	// after its final delimiter to locate the kernel start-time counter.
	end := strings.LastIndex(stat, ") ")
	if end < 0 {
		return "", fmt.Errorf("invalid proc stat")
	}
	fields := strings.Fields(stat[end+2:])
	if len(fields) < 20 || fields[0] == "Z" || fields[0] == "X" {
		return "", fmt.Errorf("target process is not alive")
	}
	return fields[19], nil
}
func configDigest(pid, path string) (string, error) {
	// Read through the process root so the digest covers the container's mounted
	// configuration rather than a same-named file in the launcher's filesystem.
	f, err := os.Open(filepath.Join("/proc", pid, "root", path))
	if err != nil {
		return "", err
	}
	defer f.Close()
	b, err := io.ReadAll(io.LimitReader(f, (4<<20)+1))
	if err != nil {
		return "", err
	}
	if len(b) > 4<<20 {
		return "", fmt.Errorf("workload config exceeds 4 MiB")
	}
	sum := sha256.Sum256(b)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

// checkConfigEnvironment binds the declared config path to the actual process
// environment. The variable name is supplied by the approved application config.
func checkConfigEnvironment(t protocol.Target) error {
	f, err := os.Open(filepath.Join("/proc", t.PID, "environ"))
	if err != nil {
		return err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, (1<<20)+1))
	if err != nil || len(data) > 1<<20 {
		return fmt.Errorf("cannot read bounded target environment")
	}
	prefix := []byte(t.ConfigEnv + "=")
	matches := 0
	for _, entry := range bytes.Split(data, []byte{0}) {
		if bytes.HasPrefix(entry, prefix) {
			if string(entry[len(prefix):]) != t.ConfigPath {
				return fmt.Errorf("target configuration environment differs from registration")
			}
			matches++
		}
	}
	if matches != 1 {
		return fmt.Errorf("target must declare its configuration path exactly once")
	}
	return nil
}

// Check rechecks process incarnation, namespace/cgroup/executable path,
// configuration bytes and listener ownership. Docker image/mount inspection
// occurs during registration/Provider collection, not in this polling check.
func Check(t protocol.Target) error {
	if err := t.Validate(); err != nil {
		return err
	}
	boot, err := os.ReadFile("/proc/sys/kernel/random/boot_id")
	if err != nil {
		return err
	}
	if strings.TrimSpace(string(boot)) != t.BootID {
		return fmt.Errorf("target belongs to another boot")
	}
	start, err := startTime(t.PID)
	if err != nil {
		return err
	}
	if start != t.StartTime {
		return fmt.Errorf("target PID was reused")
	}
	for path, want := range map[string]string{"ns/pid": t.PIDNamespace, "ns/net": t.NetNamespace, "exe": t.Executable} {
		value, err := procLink(t.PID, path)
		if err != nil {
			return err
		}
		if value != want {
			return fmt.Errorf("target %s changed", path)
		}
	}
	cgroup, err := procString(t.PID, "cgroup")
	if err != nil {
		return err
	}
	if !strings.Contains(cgroup, t.ContainerID) {
		return fmt.Errorf("target is not in registered container cgroup")
	}
	digest, err := configDigest(t.PID, t.ConfigPath)
	if err != nil {
		return err
	}
	if digest != t.ConfigDigest {
		return fmt.Errorf("workload config changed")
	}
	if err := checkConfigEnvironment(t); err != nil {
		return err
	}
	port, _ := strconv.Atoi(t.ListenPort)
	pid, err := listenerPID(t.PID, port)
	if err != nil {
		return err
	}
	if pid != t.PID {
		return fmt.Errorf("upstream is served by another process")
	}
	return nil
}

// listenerPID requires one actual owner of a loopback-only service listener.
// Container init/supervisor is not assumed to be that process.
func listenerPID(anchor string, port int) (string, error) {
	pidNS, err := procLink(anchor, "ns/pid")
	if err != nil {
		return "", err
	}
	sockets := map[string]bool{}
	for _, table := range []string{"tcp", "tcp6"} {
		data, err := procString(anchor, "net/"+table)
		if err != nil {
			return "", err
		}
		for _, line := range strings.Split(data, "\n") {
			fields := strings.Fields(line)
			if len(fields) < 10 || fields[3] != "0A" {
				continue
			}
			parts := strings.Split(fields[1], ":")
			if len(parts) != 2 {
				continue
			}
			p, _ := strconv.ParseUint(parts[1], 16, 16)
			if int(p) != port {
				continue
			}
			if table != "tcp" || parts[0] != "0100007F" {
				return "", fmt.Errorf("workload must listen only on IPv4 127.0.0.1:%d", port)
			}
			sockets[fields[9]] = true
		}
	}
	if len(sockets) != 1 {
		return "", fmt.Errorf("expected exactly one workload loopback listener")
	}
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return "", err
	}
	// A namespace TCP table lists sockets, not process owners. Resolve the
	// listener inode through open FDs instead of assuming container init owns it.
	owners := map[string]bool{}
	for _, entry := range entries {
		pid := entry.Name()
		if _, err := strconv.Atoi(pid); err != nil {
			continue
		}
		ns, err := procLink(pid, "ns/pid")
		if err != nil || ns != pidNS {
			continue
		}
		fds, err := os.ReadDir(filepath.Join("/proc", pid, "fd"))
		if err != nil {
			continue
		}
		for _, fd := range fds {
			link, err := procLink(pid, "fd/"+fd.Name())
			if err != nil {
				continue
			}
			if strings.HasPrefix(link, "socket:[") && sockets[strings.TrimSuffix(strings.TrimPrefix(link, "socket:["), "]")] {
				owners[pid] = true
			}
		}
	}
	if len(owners) != 1 {
		return "", fmt.Errorf("service listener must have exactly one process owner")
	}
	for pid := range owners {
		return pid, nil
	}
	panic("unreachable")
}

// Register observes the actual server process behind the container listener.
// Boot ID and kernel start time distinguish its lifetime from a reused PID.
func Register(ctx context.Context, containerID, agentID, workloadID, policyID, configPath, configEnv string, port int) (protocol.Target, error) {
	var result protocol.Target
	if err := protocol.ValidateAgentID(agentID); err != nil {
		return result, err
	}
	info, err := inspect(ctx, containerID)
	if err != nil {
		return result, err
	}
	if workloadID == "" || info.Config.Labels["io.trucon.workload-id"] != workloadID {
		return result, fmt.Errorf("container differs from approved workload identity")
	}
	pid, err := listenerPID(strconv.Itoa(info.State.PID), port)
	if err != nil {
		return result, err
	}
	result = protocol.Target{AgentID: agentID, ContainerID: info.ID, ImageConfigDigest: info.Image, LaunchID: info.Config.Labels["io.trucon.launch-id"], WorkloadID: workloadID, PolicyID: policyID, ConfigPath: configPath, ListenPort: strconv.Itoa(port), PID: pid, RootFSReadOnly: "true"}
	result.ConfigEnv = configEnv
	boot, err := os.ReadFile("/proc/sys/kernel/random/boot_id")
	if err != nil {
		return result, err
	}
	result.BootID = strings.TrimSpace(string(boot))
	result.StartTime, err = startTime(pid)
	if err != nil {
		return result, err
	}
	result.PIDNamespace, err = procLink(pid, "ns/pid")
	if err != nil {
		return result, err
	}
	result.NetNamespace, err = procLink(pid, "ns/net")
	if err != nil {
		return result, err
	}
	result.Executable, err = procLink(pid, "exe")
	if err != nil {
		return result, err
	}
	result.ConfigDigest, err = configDigest(pid, configPath)
	if err != nil {
		return result, err
	}
	return result, Check(result)
}

// StartWatch combines a pidfd exit notification with repeated local Check calls.
// The 500 ms poll wait excludes check/scheduling time and is not a shutdown SLA;
// this watcher does not generate Quotes or re-run Trustee appraisal.
func StartWatch(ctx context.Context, t protocol.Target) (<-chan error, error) {
	return StartWatchWithProgress(ctx, t, nil)
}

// StartWatchWithProgress reports only completed successful local checks. The
// callback must not block; callers can use this progress to supervise a stuck
// check independently from the watcher. It does not re-attest the workload.
func StartWatchWithProgress(ctx context.Context, t protocol.Target, checked func(time.Time)) (<-chan error, error) {
	pid, err := strconv.Atoi(t.PID)
	if err != nil {
		return nil, err
	}
	// Open the lifetime handle before checking registration so an exit/reuse
	// between those steps cannot leave the watcher following only a numeric PID.
	fd, err := unix.PidfdOpen(pid, 0)
	if err != nil {
		return nil, fmt.Errorf("open target pidfd: %w", err)
	}
	if err = observedCheck(t, Check, checked); err != nil {
		_ = unix.Close(fd)
		return nil, err
	}
	result := make(chan error, 1)
	go func() {
		defer unix.Close(fd)
		result <- watchFD(ctx, t, fd, func(t protocol.Target) error {
			return observedCheck(t, Check, checked)
		})
	}()
	return result, nil
}

func observedCheck(t protocol.Target, check func(protocol.Target) error, checked func(time.Time)) error {
	if err := check(t); err != nil {
		return err
	}
	if checked != nil {
		checked(time.Now())
	}
	return nil
}
func Watch(ctx context.Context, t protocol.Target) error {
	result, err := StartWatch(ctx, t)
	if err != nil {
		return err
	}
	return <-result
}
func watchFD(ctx context.Context, t protocol.Target, fd int, check func(protocol.Target) error) error {
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := check(t); err != nil {
			return err
		}
		fds := []unix.PollFd{{Fd: int32(fd), Events: unix.POLLIN}}
		n, err := unix.Poll(fds, 500)
		if errors.Is(err, syscall.EINTR) {
			continue
		}
		if err != nil {
			return err
		}
		if n > 0 {
			return fmt.Errorf("target process exited")
		}
	}
}
