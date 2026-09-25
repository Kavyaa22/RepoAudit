"""Q&A chat endpoint with RAG."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from app.core.security.deps import CurrentUser, get_current_user
from app.modules.github.shared.users import resolve_user_id
from repoaudit.interfaces.api.schemas import ChatRequest
from repoaudit.interfaces.api.runtime import ensure_project_context, owned_by_user
from repoaudit.platform.config import Config, resolve_model

router = APIRouter()
logger = logging.getLogger(__name__)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _error_stream(message: str):
    async def event_stream():
        yield _sse({"error": message})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/project/{project_id}/chat")
async def chat(
    project_id: str,
    req: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    x_api_key: str | None = Header(None),
    x_model: str | None = Header(None),
    x_language: str | None = Header(None),
):
    """SSE streaming chat response with RAG retrieval."""
    user_id = resolve_user_id(user)
    if not user_id:
        return _error_stream("Sign in required.")
    proj, project = await ensure_project_context(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return _error_stream("Project not found. Open a scanned repository from the dashboard first.")
    if project is None:
        return _error_stream(
            "Project source code is not loaded. Re-run a scan on this repository, "
            "then try chat again."
        )

    # Build RAG index when missing or after project re-ingest.
    file_sig = len(project.files)
    if proj.get("rag_file_count") != file_sig or "rag" not in proj:
        from repoaudit.retrieval.lexical import SimpleRAG

        rag = SimpleRAG()
        rag.index(project)
        proj["rag"] = rag
        proj["rag_file_count"] = file_sig
    rag = proj["rag"]

    chunks = rag.retrieve(req.question, top_k=5)
    context_parts = []
    references = []
    for chunk in chunks:
        context_parts.append(
            f"### {chunk.file_path} (lines {chunk.line_start}-{chunk.line_end})\n"
            f"```\n{chunk.content}\n```"
        )
        references.append({
            "path": chunk.file_path,
            "line_start": chunk.line_start,
            "line_end": chunk.line_end,
            "snippet": chunk.content[:200],
        })

    if not context_parts:
        context_text = (
            "_No indexed source chunks matched this query. "
            "Answer from general engineering knowledge and ask the user to re-scan if code seems missing._"
        )
    else:
        context_text = "\n\n".join(context_parts)

    cfg = Config.load()
    if x_api_key:
        cfg.api_key = x_api_key
    if x_model:
        resolved = resolve_model(x_model)
        cfg.model = resolved
        cfg.model_chat = resolved
    if x_language:
        cfg.language = x_language

    if not cfg.api_key:
        return _error_stream(
            "No API key configured. Add your OpenRouter key in Settings or set OPENROUTER_API_KEY in backend/.env."
        )

    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.llm.prompts import build_chat_prompt

    llm = LLMClient(
        model=cfg.model,
        api_key=cfg.api_key,
        api_base=cfg.api_base,
        operation_models=cfg.get_operation_models(),
    )
    messages = build_chat_prompt(req.question, context_text, cfg.language)

    async def event_stream():
        yield _sse({"references": references})

        got_content = False
        try:
            async for chunk in llm.stream(messages, operation="chat"):
                if chunk:
                    got_content = True
                    yield _sse({"content": chunk})
        except Exception as exc:
            logger.exception("Chat stream failed for project %s", project_id)
            yield _sse({"error": f"LLM stream failed: {exc}"})
            yield _sse({"done": True})
            return

        if not got_content:
            yield _sse({
                "error": (
                    "The model returned an empty response. Try a different model in Settings "
                    "or check your OpenRouter quota."
                )
            })

        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
