from fastapi import APIRouter

from .. import workflows


router = APIRouter()

router.add_api_route(
    "/api/deploy-launch",
    workflows.deploy_launch,
    methods=["POST"],
    response_model=workflows.LaunchResponse,
)
router.add_api_route(
    "/api/deploy-launch/commit/{launch_id}",
    workflows.complete_launch_commit,
    methods=["POST"],
    response_model=workflows.LaunchResult,
)
router.add_api_route(
    "/api/launch-result/{launch_id}",
    workflows.get_launch_result,
    methods=["GET"],
    response_model=workflows.LaunchResult,
)
