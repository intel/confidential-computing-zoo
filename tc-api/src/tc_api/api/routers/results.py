from fastapi import APIRouter

from .. import results_support


router = APIRouter()

router.add_api_route("/", results_support.root, methods=["GET"])
router.add_api_route(
    "/api/transparency-log/{log_id}",
    results_support.get_transparency_log,
    methods=["GET"],
    response_model=results_support.TransparencyResult,
)
router.add_api_route(
    "/api/get-summaryTransparencylog",
    results_support.get_summary_transparencylog,
    methods=["POST"],
    response_model=results_support.SummaryTransparencyRespone,
)
