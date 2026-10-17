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

// argus-workload records and checks the real service process on its Linux host.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/target"
	"os"
	"path/filepath"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run() error {
	action := flag.String("action", "check", "register or check")
	registration := flag.String("registration", "", "required root-owned registration")
	container := flag.String("container", "", "full Docker container ID")
	agent := flag.String("agent-id", "", "approved SPIRE Agent identity")
	workload := flag.String("workload-id", "", "approved workload identity")
	policy := flag.String("policy", "", "fixed workload policy")
	config := flag.String("config", "", "actual workload configuration path")
	configEnv := flag.String("config-env", "", "environment variable naming the active configuration path")
	port := flag.Int("port", 0, "single IPv4 loopback service port")
	flag.Parse()
	if !filepath.IsAbs(*registration) {
		return fmt.Errorf("registration path must be absolute")
	}
	switch *action {
	case "check":
		t, err := target.Load(*registration)
		if err != nil {
			return err
		}
		if err = target.Check(t); err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(t)
	case "register":
		if !filepath.IsAbs(*registration) {
			return fmt.Errorf("registration path must be absolute")
		}
		t, err := target.Register(context.Background(), *container, *agent, *workload, *policy, *config, *configEnv, *port)
		if err != nil {
			return err
		}
		// Never overwrite a live registration. Operator must stop Helper/NGINX and
		// remove the previous registration before registering a replacement launch.
		f, err := os.OpenFile(*registration, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			return err
		}
		ok := false
		defer func() {
			_ = f.Close()
			if !ok {
				_ = os.Remove(*registration)
			}
		}()
		if err = json.NewEncoder(f).Encode(t); err != nil {
			return err
		}
		if err = f.Sync(); err != nil {
			return err
		}
		ok = true
		return json.NewEncoder(os.Stdout).Encode(t)
	default:
		return fmt.Errorf("unknown action")
	}
}
