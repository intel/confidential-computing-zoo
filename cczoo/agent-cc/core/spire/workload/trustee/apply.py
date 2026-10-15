#!/usr/bin/env python3
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Apply the small AS hook to the reviewed upstream source; refuse other bases."""
import hashlib
from pathlib import Path
import sys

# Pin the reviewed source layout so the hook cannot silently move before Quote
# verification or outside the intended appraisal path on another Trustee base.
BASE_SHA256 = "13c5742c6fdce30e5ab12f52dd5787bce66b26f442cc591d5ace2f8717202f48"
HERE = Path(__file__).resolve().parent


def apply(root):
    source = root / "attestation-service/src/lib.rs"
    original = source.read_bytes()
    module = source.with_name("argus_trucon.rs")
    if "mod argus_trucon;" in original.decode():
        raise ValueError("hook already present; use a clean reviewed Trustee checkout")
    if hashlib.sha256(original).hexdigest() != BASE_SHA256:
        raise ValueError("Trustee source differs from the reviewed base; refusing automatic patch")
    text = original.decode().replace("pub mod config;", "pub mod config;\nmod argus_trucon;", 1)
    anchor = "            let claims = verifier\n"
    assert text.count(anchor) == 1
    text = text.replace(anchor, "            let trucon_request = argus_trucon::prepare(\n"
        "                &verification_request.tee, &verification_request.evidence,\n"
        "                &runtime_data_claims, &verification_request.runtime_data_hash_algorithm,\n"
        "            )?;\n" + anchor, 1)
    anchor = "            for (claims_from_tee_evidence, tee_class) in claims {"
    assert text.count(anchor) == 1
    text = text.replace(anchor, "            for (mut claims_from_tee_evidence, tee_class) in claims {\n"
        "                argus_trucon::appraise(trucon_request.as_ref(), &mut claims_from_tee_evidence, &tee_class).await?;", 1)
    cargo = root / "attestation-service/Cargo.toml"
    cargo_text = cargo.read_text()
    assert cargo_text.count("tokio.workspace = true") == 1
    cargo_text = cargo_text.replace("tokio.workspace = true", 'tokio = { workspace = true, features = ["process", "io-util", "time", "sync"] }')
    module.write_bytes((HERE / "argus_trucon.rs").read_bytes())
    source.write_text(text, encoding="utf-8", newline="\n")
    cargo.write_text(cargo_text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    apply(Path(sys.argv[1]).resolve())
