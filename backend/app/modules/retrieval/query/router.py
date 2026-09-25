"""Router for retrieval.query."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.retrieval.query import service
from app.modules.retrieval.query.schema import QueryRequest, QueryResponse

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/query", response_model=ApiResponse[QueryResponse])
async def query_endpoint(payload: QueryRequest) -> ApiResponse[QueryResponse]:
    result = await service.execute(payload)
    return ApiResponse(data=result)
