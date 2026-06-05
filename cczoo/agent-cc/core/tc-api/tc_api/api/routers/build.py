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
