"""litellm wrapper for repoaudit."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator

import litellm

litellm.suppress_debug_info = True

logger = logging.getLogger(__name__)


class LLMClient:
    """async LLM client backed by litellm with operation-tier model support."""

    def __init__(
        self,
        model: str,
        api_key: str = "",
        api_base: str = "",
        operation_models: dict[str, str] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.api_base = api_base or None
        self.operation_models = operation_models or {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0

    def resolve_target_model(self, operation: str | None = None, model_override: str | None = None) -> str:
        if model_override:
            return model_override
        if operation and operation in self.operation_models:
            return self.operation_models[operation]
        return self.model

    async def complete(
        self,
        messages: list[dict],
        *,
        operation: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        """non-streaming completion, returns the full response text."""
        target_model = self.resolve_target_model(operation, model)
        kwargs: dict = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if response_format:
            kwargs["response_format"] = response_format

        current_max_tokens = max_tokens
        resp = None
        for attempt in range(3):
            kwargs["max_tokens"] = current_max_tokens
            try:
                resp = await litellm.acompletion(**kwargs)
                break
            except Exception as e:
                err_msg = str(e)
                if ("402" in err_msg or "fewer max_tokens" in err_msg) and current_max_tokens > 300:
                    match = re.search(r"afford (\d+)", err_msg)
                    if match:
                        current_max_tokens = max(250, int(match.group(1)) - 50)
                    else:
                        current_max_tokens = max(250, current_max_tokens // 2)
                    logger.warning(
                        "OpenRouter balance limit hit; retrying with max_tokens=%d (attempt %d/3)",
                        current_max_tokens,
                        attempt + 1,
                    )
                    continue
                logger.error("LLM call failed: %s", e)
                return f"[LLM Error: {e}]"

        if resp is None:
            return "[LLM Error: OpenRouter token limit exceeded]"

        usage = resp.usage
        if usage:
            self.total_input_tokens += usage.prompt_tokens or 0
            self.total_output_tokens += usage.completion_tokens or 0
        # litellm cost tracking
        try:
            cost = litellm.completion_cost(completion_response=resp)
            self.total_cost += cost
        except Exception:
            pass

        return resp.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        *,
        operation: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """streaming completion, yields text chunks."""
        target_model = self.resolve_target_model(operation, model)
        kwargs: dict = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        elif target_model.startswith("openrouter/"):
            kwargs["api_base"] = "https://openrouter.ai/api/v1"

        current_max_tokens = max_tokens
        resp = None
        for attempt in range(3):
            kwargs["max_tokens"] = current_max_tokens
            try:
                resp = await litellm.acompletion(**kwargs)
                break
            except Exception as e:
                err_msg = str(e)
                if ("402" in err_msg or "fewer max_tokens" in err_msg) and current_max_tokens > 300:
                    match = re.search(r"afford (\d+)", err_msg)
                    if match:
                        current_max_tokens = max(250, int(match.group(1)) - 50)
                    else:
                        current_max_tokens = max(250, current_max_tokens // 2)
                    logger.warning(
                        "OpenRouter balance limit hit; retrying stream with max_tokens=%d (attempt %d/3)",
                        current_max_tokens,
                        attempt + 1,
                    )
                    continue
                logger.error("LLM stream failed: %s", e)
                yield f"[LLM Error: {e}]"
                return

        if resp is None:
            yield "[LLM Error: OpenRouter token limit exceeded]"
            return

        try:
            async for chunk in resp:
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                text = None
                if delta is not None:
                    text = getattr(delta, "content", None)
                if not text and hasattr(choice, "message") and choice.message:
                    text = getattr(choice.message, "content", None)
                if not text:
                    text = getattr(choice, "text", None)
                if text:
                    yield text
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            yield f"[LLM Error: {e}]"
