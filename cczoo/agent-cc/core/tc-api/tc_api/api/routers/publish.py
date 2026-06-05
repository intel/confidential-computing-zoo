from fastapi import APIRouter

from .. import workflows


router = APIRouter()

router.add_api_route(
    "/api/publish-package",
    workflows.publish_package,
    methods=["POST"],
    response_model=workflows.PublishPackageResponse,
)
router.add_api_route(
    "/api/publish-package/commit/{build_id}",
    workflows.complete_publish_commit,
    methods=["POST"],
    response_model=workflows.PublishPackageResponse,
)
router.add_api_route(
    "/api/publish-result/{build_id}",
    workflows.get_publish_result,
    methods=["GET"],
    response_model=workflows.PublishResult,
)
