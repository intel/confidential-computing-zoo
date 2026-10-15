package sidecar

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/jwtbundle"
	"github.com/spiffe/go-spiffe/v2/svid/jwtsvid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/spiffe/spiffe-helper/pkg/disk"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"k8s.io/apimachinery/pkg/util/wait"
	"k8s.io/client-go/util/retry"
)

var (
	backoff = wait.Backoff{
		Steps:    10,
		Duration: 10 * time.Millisecond,
		Factor:   5.0,
		Jitter:   0.1,
	}
)

func (s *Sidecar) watchX509Context(ctx context.Context) error {
	err := s.client.WatchX509Context(ctx, &x509Watcher{sidecar: s})
	if err != nil && !errors.Is(err, context.Canceled) {
		return fmt.Errorf("watching X.509 context: %w", err)
	}

	return nil
}

func (s *Sidecar) watchJWTBundles(ctx context.Context) error {
	err := s.client.WatchJWTBundles(ctx, &JWTBundlesWatcher{sidecar: s})
	if err != nil && !errors.Is(err, context.Canceled) {
		return fmt.Errorf("watching JWT bundle updates: %w", err)
	}

	return nil
}

func (s *Sidecar) watchJWTSVIDs(ctx context.Context) error {
	var wg sync.WaitGroup
	for _, jwtConfig := range s.config.JWTSVIDs {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.updateJWTSVID(ctx, jwtConfig.JWTAudience, jwtConfig.JWTExtraAudiences, jwtConfig.JWTSVIDFilename)
		}()
	}

	wg.Wait()

	return nil
}

func (s *Sidecar) fetchAndWriteX509Context(ctx context.Context) error {
	var x509Context *workloadapi.X509Context

	// Retry PermissionDenied errors. We may get a few of these before the cert is minted
	err := retry.OnError(backoff, func(err error) bool {
		return status.Code(err) == codes.PermissionDenied
	}, func() (err error) {
		x509Context, err = s.client.FetchX509Context(ctx)
		return err
	})
	if err != nil {
		return err
	}

	return disk.WriteX509Context(x509Context, s.config.AddIntermediatesToBundle, s.config.IncludeFederatedDomains, s.config.OmitExpired, s.config.CertDir, s.config.SVIDFilename, s.config.SVIDKeyFilename, s.config.SVIDBundleFilename, s.config.CertFileMode, s.config.KeyFileMode, s.config.Hint)
}

func (s *Sidecar) fetchAndWriteJWTBundle(ctx context.Context) error {
	var jwtBundleSet *jwtbundle.Set

	// Retry PermissionDenied errors. We may get a few of these before the cert is minted
	err := retry.OnError(backoff, func(err error) bool {
		return status.Code(err) == codes.PermissionDenied
	}, func() (err error) {
		jwtBundleSet, err = s.client.FetchJWTBundles(ctx)
		return err
	})
	if err != nil {
		return err
	}

	return disk.WriteJWTBundleSet(jwtBundleSet, s.config.CertDir, s.config.JWTBundleFilename, s.config.JWTBundleFileMode)
}

func (s *Sidecar) fetchAndWriteJWTSVIDs(ctx context.Context) error {
	var errs []error
	for _, jwtConfig := range s.config.JWTSVIDs {
		if err := s.fetchAndWriteJWTSVID(ctx, jwtConfig.JWTAudience, jwtConfig.JWTSVIDFilename); err != nil {
			errs = append(errs, fmt.Errorf("unable to fetch JWT SVID for audience %q: %w", jwtConfig.JWTAudience, err))
		}
	}

	return errors.Join(errs...)
}

func (s *Sidecar) fetchAndWriteJWTSVID(ctx context.Context, audience, jwtSVIDFilename string) error {
	var jwtSVIDs []*jwtsvid.SVID

	// Retry PermissionDenied errors. We may get a few of these before the cert is minted
	err := retry.OnError(backoff, func(err error) bool {
		return status.Code(err) == codes.PermissionDenied
	}, func() (err error) {
		jwtSVIDs, err = s.jwtSource.FetchJWTSVIDs(ctx, jwtsvid.Params{Audience: audience})
		return err
	})
	if err != nil {
		return err
	}

	return disk.WriteJWTSVID(jwtSVIDs, s.config.CertDir, jwtSVIDFilename, s.config.JWTSVIDFileMode, s.config.Hint)
}
