# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from fastapi import APIRouter

from .. import workflows


router = APIRouter()

router.add_api_route(
    "/api/build-package",
    workflows.build_package,
    methods=["POST"],
    response_model=workflows.BuildPackageResponse,
)
router.add_api_route(
    "/api/build-result/{build_id}",
    workflows.get_build_result,
    methods=["GET"],
    response_model=workflows.BuildResult,
)
router.add_api_route(
    "/api/build-package/commit/{build_id}",
    workflows.complete_build_commit,
    methods=["POST"],
    response_model=workflows.BuildPackageResponse,
)
