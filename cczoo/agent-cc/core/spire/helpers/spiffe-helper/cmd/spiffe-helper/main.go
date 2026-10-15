package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/sirupsen/logrus"
	"github.com/spiffe/spiffe-helper/cmd/spiffe-helper/config"
	"github.com/spiffe/spiffe-helper/pkg/broker"
	"github.com/spiffe/spiffe-helper/pkg/health"
	"github.com/spiffe/spiffe-helper/pkg/sidecar"
	"github.com/spiffe/spiffe-helper/pkg/util"
	"github.com/spiffe/spiffe-helper/pkg/version"
)

const (
	daemonModeFlagName = "daemon-mode"
)

func main() {
	versionFlag := flag.Bool("version", false, "print version")
	configFile := flag.String("config", "helper.conf", "<configFile> Configuration file path")
	daemonModeFlag := flag.Bool(daemonModeFlagName, true, "Toggle running as a daemon to rotate X.509/JWT or just fetch and exit")
	flag.Parse()

	if *versionFlag {
		fmt.Println(version.Version())
		os.Exit(0)
	}

	log := logrus.WithField("system", "spiffe-helper")

	log.Infof("Using configuration file: %q", *configFile)
	hclConfig, err := config.ParseConfig(*configFile, *daemonModeFlag, daemonModeFlagName)
	if err != nil {
		log.WithError(err).Errorf("failed to parse configuration")
		os.Exit(1)
	}

	if err := hclConfig.ValidateConfig(log); err != nil {
		log.WithError(err).Errorf("invalid configuration")
		os.Exit(1)
	}

	if err = startSidecar(hclConfig, log); err != nil {
		log.WithError(err).Errorf("Error starting spiffe-helper")
		os.Exit(1)
	}

	log.Infof("Exiting")
	os.Exit(0)
}

func startSidecar(hclConfig *config.Config, log logrus.FieldLogger) error {
	sidecarConfig := config.NewSidecarConfig(hclConfig, log)
	spiffeSidecar := sidecar.New(sidecarConfig)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if hclConfig.Broker != nil {
		// Broker mode owns publication and target supervision. Keep the upstream
		// Workload API sidecar lifecycle separate when this opt-in block is absent.
		return broker.Run(ctx, hclConfig.AgentAddress, hclConfig.CertDir, *hclConfig.Broker)
	}

	if !*hclConfig.DaemonMode {
		log.Info("Daemon mode disabled")
		return spiffeSidecar.Run(ctx)
	}

	log.Info("Launching daemon")
	tasks := []func(context.Context) error{
		spiffeSidecar.RunDaemon,
	}

	if hclConfig.HealthCheck.ListenerEnabled {
		healthServer := health.New(&hclConfig.HealthCheck, log, spiffeSidecar)
		tasks = append(tasks, healthServer.Start)
	}

	err := util.RunTasks(ctx, tasks...)
	if errors.Is(err, context.Canceled) {
		return nil
	}

	return err
}
