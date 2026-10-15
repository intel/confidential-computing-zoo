package broker

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"
)

type watchdog struct {
	interval     time.Duration
	invocationID string
	notify       func() error
}

// watchdogFromEnvironment uses systemd's own invocation and notification socket.
// Managed mode rejects missing supervision. Without watchdog settings, unmanaged
// runs use a correlation ID and the in-process progress checks run by runHealth.
func watchdogFromEnvironment() (watchdog, error) {
	w := watchdog{interval: 500 * time.Millisecond}
	w.invocationID = os.Getenv("INVOCATION_ID")
	usec := os.Getenv("WATCHDOG_USEC")
	required := os.Getenv("ARGUS_REQUIRE_SYSTEMD_WATCHDOG") == "1"
	if usec == "" {
		if required {
			return w, fmt.Errorf("systemd watchdog is required but WATCHDOG_USEC is missing")
		}
		if w.invocationID == "" {
			b := make([]byte, 16)
			if _, err := rand.Read(b); err != nil {
				return w, err
			}
			w.invocationID = hex.EncodeToString(b)
		}
		return w, nil
	}
	if len(w.invocationID) != 32 || strings.Trim(w.invocationID, "0123456789abcdef") != "" {
		return w, fmt.Errorf("systemd watchdog requires a valid INVOCATION_ID")
	}
	micros, err := strconv.ParseInt(usec, 10, 64)
	if err != nil || micros < 3000 || micros > int64(time.Hour/time.Microsecond) {
		return w, fmt.Errorf("invalid systemd WATCHDOG_USEC")
	}
	if pid := os.Getenv("WATCHDOG_PID"); pid != "" && pid != strconv.Itoa(os.Getpid()) {
		return w, fmt.Errorf("systemd WATCHDOG_PID does not name this Helper")
	}
	socket := os.Getenv("NOTIFY_SOCKET")
	if len(socket) < 2 || (socket[0] != '/' && socket[0] != '@') {
		return w, fmt.Errorf("systemd watchdog requires an absolute or abstract NOTIFY_SOCKET")
	}
	if interval := time.Duration(micros) * time.Microsecond / 3; interval < w.interval {
		// Leave time for scheduling and bounded socket writes before systemd's
		// watchdog expires; this interval is not an attestation refresh period.
		w.interval = interval
	}
	w.notify = func() error {
		conn, err := net.DialUnix("unixgram", nil, &net.UnixAddr{Name: socket, Net: "unixgram"})
		if err != nil {
			return err
		}
		defer conn.Close()
		if err = conn.SetWriteDeadline(time.Now().Add(100 * time.Millisecond)); err != nil {
			return err
		}
		_, err = conn.Write([]byte("WATCHDOG=1"))
		return err
	}
	return w, nil
}
