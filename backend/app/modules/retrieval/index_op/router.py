"""Router for retrieval.index_op."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.retrieval.index_op import service
from app.modules.retrieval.index_op.schema import IndexOpRequest, IndexOpResponse

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/index/ops", response_model=ApiResponse[IndexOpResponse])
async def index_op_endpoint(payload: IndexOpRequest) -> ApiResponse[IndexOpResponse]:
    result = await service.execute(payload)
    return ApiResponse(data=result)
