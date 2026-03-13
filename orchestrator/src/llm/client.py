"""Provider-agnostic async LLM client — copied from DeepResearch."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import httpx

from ..config import LLMConfig

log = logging.getLogger(__name__)

_OPENAI_PROVIDERS = {"vllm", "openai", "ollama"}
_RETRY_ATTEMPTS = 3
_TIMEOUT = 1800.0


@dataclass
class CompletionResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMClient:
    """Supports OpenAI-compatible endpoints (vLLM, OpenAI, Ollama) and Anthropic."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._is_anthropic = config.provider == "anthropic"
        headers: dict[str, str] = {}
        if self._is_anthropic:
            headers["x-api-key"] = config.api_key
            headers["anthropic-version"] = "2023-06-01"
        elif config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        headers["Content-Type"] = "application/json"
        self._http = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(_TIMEOUT, connect=10.0),
        )

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float = 0.3,
        json_schema: dict | None = None,
        thinking: bool = True,
    ) -> CompletionResult:
        max_tokens = max_tokens or self.config.max_tokens
        if self._is_anthropic:
            return await self._complete_anthropic(messages, max_tokens, temperature, json_schema)
        return await self._complete_openai(messages, max_tokens, temperature, json_schema, thinking)

    async def close(self) -> None:
        await self._http.aclose()

    # -- OpenAI-compatible path -------------------------------------------

    async def _complete_openai(
        self, messages: list[dict], max_tokens: int, temperature: float,
        json_schema: dict | None, thinking: bool = True,
    ) -> CompletionResult:
        url = f"{self.config.api_url.rstrip('/')}/chat/completions"
        body: dict = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if not thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": json_schema},
            }
        return await self._post_with_retry(url, body, extractor=_extract_openai)

    # -- Anthropic path ---------------------------------------------------

    async def _complete_anthropic(
        self, messages: list[dict], max_tokens: int, temperature: float,
        json_schema: dict | None,
    ) -> CompletionResult:
        url = f"{self.config.api_url.rstrip('/')}/messages"
        system_text = ""
        chat_msgs: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                chat_msgs.append({"role": m["role"], "content": m["content"]})

        body: dict = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_msgs,
        }
        if system_text:
            body["system"] = system_text.strip()
        if json_schema is not None:
            body["tools"] = [{
                "name": "json_response",
                "description": "Return the structured JSON response.",
                "input_schema": json_schema,
            }]
            body["tool_choice"] = {"type": "tool", "name": "json_response"}

        return await self._post_with_retry(url, body, extractor=_extract_anthropic)

    # -- Retry logic ------------------------------------------------------

    async def _post_with_retry(self, url: str, body: dict, extractor) -> CompletionResult:
        last_err: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = await self._http.post(url, json=body)
                resp.raise_for_status()
                return extractor(resp.json())
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError, IndexError) as exc:
                last_err = exc
                wait = 2 ** attempt
                log.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, _RETRY_ATTEMPTS, exc, wait,
                )
                if attempt < _RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(wait)
        raise RuntimeError(f"LLM request failed after {_RETRY_ATTEMPTS} attempts: {last_err}")


# -- Response extractors --------------------------------------------------

def _extract_openai(data: dict) -> CompletionResult:
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    text = content if content else (reasoning or "")
    usage = data.get("usage", {})
    return CompletionResult(
        text=text,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )


def _extract_anthropic(data: dict) -> CompletionResult:
    text = ""
    for block in data.get("content", []):
        if block["type"] == "tool_use":
            text = json.dumps(block["input"])
            break
        if block["type"] == "text":
            text = block["text"]
            break
    usage = data.get("usage", {})
    return CompletionResult(
        text=text,
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    )
