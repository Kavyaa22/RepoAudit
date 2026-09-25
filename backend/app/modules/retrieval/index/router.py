"""Router for retrieval.index."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.retrieval.index import service
from app.modules.retrieval.index.schema import IndexRequest, IndexResponse

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/index", response_model=ApiResponse[IndexResponse])
async def index_endpoint(payload: IndexRequest) -> ApiResponse[IndexResponse]:
    result = await service.execute(payload)
    return ApiResponse(data=result)
