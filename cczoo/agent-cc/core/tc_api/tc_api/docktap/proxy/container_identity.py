# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bind a lifecycle operation to the daemon's full ID before it takes effect."""
import json
import re
from urllib.parse import quote, unquote

from ...trucon.internal_transport import UnixSocketHTTPConnection

FULL_ID = re.compile(r"[0-9a-f]{64}\Z")
MAX_INSPECT_BYTES = 1024 * 1024


def bind_container_target(request_data, record, socket_path):
    """Return a request pinned to the same ID that will enter the signed log.

    Resolve before stop/rm (after rm inspect is impossible). Forwarding the
    original alias after inspecting it would allow a concurrent rename to
    change the operation's target, so rewrite just the request-line reference.
    """
    first, separator, rest = request_data.partition(b"\r\n")
    method, path, protocol = first.split(b" ", 2)
    match = re.fullmatch(rb"(/(?:v[0-9]+\.[0-9]+/)?containers/)([^/?]+)(.*)", path)
    if not separator or match is None:
        raise ValueError("invalid lifecycle request path")
    reference = unquote(match[2].decode("ascii"), errors="strict")
    inspect_path = "/containers/" + quote(reference, safe="") + "/json"
    connection = UnixSocketHTTPConnection(socket_path, timeout=5)
    try:
        connection.request("GET", inspect_path, headers={"Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("container identity lookup failed")
        raw = response.read(MAX_INSPECT_BYTES + 1)
        if len(raw) > MAX_INSPECT_BYTES:
            raise ValueError("container inspection exceeds size limit")
        observed = json.loads(raw)
    finally:
        connection.close()
    container_id = observed.get("Id")
    if not isinstance(container_id, str) or not FULL_ID.fullmatch(container_id):
        raise ValueError("daemon did not return a full container ID")
    record.container["id"] = container_id
    # Preserve headers and body bytes; only pin the request-line target to the
    # daemon identity that will be recorded for this lifecycle operation.
    pinned_path = match[1] + container_id.encode("ascii") + match[3]
    return b" ".join((method, pinned_path, protocol)) + separator + rest
