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

// Package protocol uses the frozen contract shared with Helper and the Provider.
package protocol

import shared "github.com/intel/confidential-computing-zoo/cczoo/agent-cc/core/spire/workload/protocol"

const Name = shared.Name

type Target = shared.Target
type RuntimeData = shared.RuntimeData
type EvidenceRequest = shared.EvidenceRequest
type Evidence = shared.Evidence

var Decode = shared.Decode
var ValidateAgentID = shared.ValidateAgentID
var ValidateRekorReferences = shared.ValidateRekorReferences
var ValidateNonce = shared.ValidateNonce
var LogEvent = shared.LogEvent
