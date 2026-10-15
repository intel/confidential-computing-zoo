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

package target

import (
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"
)

// Load accepts a bounded registration protected by root ownership and directory
// permissions. Callers must still check its live process and approved baseline.
func Load(path string) (protocol.Target, error) {
	var result protocol.Target
	info, err := os.Lstat(path)
	if err != nil {
		return result, err
	}
	if !info.Mode().IsRegular() || info.Size() > 32768 {
		return result, fmt.Errorf("target registration must be a small regular file")
	}
	if err = checkOwner(info); err != nil {
		return result, err
	}
	parent, err := os.Stat(filepath.Dir(path))
	if err != nil {
		return result, err
	}
	if err = checkOwner(parent); err != nil {
		return result, err
	}
	f, err := os.Open(path)
	if err != nil {
		return result, err
	}
	defer f.Close()
	actual, err := f.Stat()
	if err != nil {
		return result, err
	}
	if !os.SameFile(info, actual) {
		// Reject replacement between the path inspection and opening the file.
		return result, fmt.Errorf("registration changed while opening")
	}
	b, err := io.ReadAll(io.LimitReader(f, 32769))
	if err != nil {
		return result, err
	}
	if len(b) > 32768 {
		return result, fmt.Errorf("registration exceeds limit")
	}
	if err = protocol.Decode(b, &result); err != nil {
		return result, err
	}
	return result, result.Validate()
}
