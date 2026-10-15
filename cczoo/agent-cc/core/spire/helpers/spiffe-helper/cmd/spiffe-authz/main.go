package main

import (
	"context"
	"flag"
	"fmt"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/spiffe-helper/pkg/authz"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

type identities []spiffeid.ID

func (ids *identities) String() string {
	var values []string
	for _, id := range *ids {
		values = append(values, id.String())
	}
	return strings.Join(values, ",")
}

func (ids *identities) Set(value string) error {
	id, err := spiffeid.FromString(value)
	if err != nil {
		return err
	}
	if id.Path() == "" {
		return fmt.Errorf("client ID must have an exact workload path")
	}
	for _, have := range *ids {
		if have == id {
			return fmt.Errorf("duplicate client ID")
		}
	}
	*ids = append(*ids, id)
	return nil
}

func main() {
	socket := flag.String("socket", "", "required protected local UDS")
	var clients identities
	flag.Var(&clients, "client-id", "exact allowed client SPIFFE ID; repeat for multiple clients")
	flag.Parse()
	if !filepath.IsAbs(*socket) || filepath.Clean(*socket) != *socket {
		log.Fatal("socket must be a clean absolute path")
	}
	if len(clients) == 0 {
		log.Fatal("at least one -client-id is required")
	}
	if st, err := os.Lstat(*socket); err == nil {
		if st.Mode()&os.ModeSocket == 0 {
			log.Fatal("socket path is not a socket")
		}
		if err = os.Remove(*socket); err != nil {
			log.Fatal(err)
		}
	} else if !os.IsNotExist(err) {
		log.Fatal(err)
	}
	// This handler trusts NGINX's TLS-derived headers, so deployment must protect
	// the parent directory and restrict access to this local socket.
	listener, err := net.Listen("unix", *socket)
	if err != nil {
		log.Fatal(err)
	}
	defer listener.Close()
	if err = os.Chmod(*socket, 0660); err != nil {
		log.Fatal(err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	server := &http.Server{Handler: authz.HandlerForIDs(clients), ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 2 * time.Second, WriteTimeout: 2 * time.Second, IdleTimeout: 5 * time.Second, MaxHeaderBytes: 64 << 10}
	go func() { <-ctx.Done(); _ = server.Close() }()
	if err = server.Serve(listener); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
