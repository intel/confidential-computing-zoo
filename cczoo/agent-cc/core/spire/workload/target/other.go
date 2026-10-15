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

//go:build !linux

package target

import (
	"context"
	"fmt"
	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
	"os"
	"time"
)

// These stubs permit cross-platform builds and schema inspection. Runtime
// attestation and process watching remain unavailable without Linux primitives.
func checkOwner(os.FileInfo) error { return nil }
func Check(protocol.Target) error  { return fmt.Errorf("target validation requires Linux") }
func Register(context.Context, string, string, string, string, string, string, int) (protocol.Target, error) {
	return protocol.Target{}, fmt.Errorf("target registration requires Linux")
}
func StartWatch(context.Context, protocol.Target) (<-chan error, error) {
	return nil, fmt.Errorf("target watching requires Linux")
}
func StartWatchWithProgress(context.Context, protocol.Target, func(time.Time)) (<-chan error, error) {
	return nil, fmt.Errorf("target watching requires Linux")
}
func Watch(context.Context, protocol.Target) error {
	return fmt.Errorf("pidfd monitoring requires Linux")
}
