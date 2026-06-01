"""Thin async wrapper around the Anthropic Messages API (streaming)."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


class AuthError(Exception):
    """401/403 from the API — not retried."""


class ContextOverflowError(Exception):
    """context_length_exceeded — surfaced to the user, not retried."""


class RetryExhaustedError(Exception):
    """Retries used up; last error is in __cause__."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


_RETRIABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
_MAX_RETRIES = 3
# Exponential-backoff base, in seconds. Production should use 1.0s so the
# 429/5xx/529 retries don't hammer the API; tests can set the env var
# `MINI_AGENT_LLM_BACKOFF_BASE=0.01` (or monkeypatch this constant) to
# keep test suites fast. Default 1.0 follows Anthropic's published
# guidance to respect `retry-after` headers.
_BACKOFF_BASE = float(os.environ.get("MINI_AGENT_LLM_BACKOFF_BASE", "1.0"))


class _RetriableError(Exception):
    """Internal marker for errors that should trigger backoff + retry."""


class LLMClient:
    def __init__(
        self, api_key: str, base_url: str, model: str, timeout: float = 60.0
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def stream_step(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        """One assistant turn with retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._stream_step_once(messages, tools)
            except _RetriableError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue
                break
        raise RetryExhaustedError(
            f"Exhausted {_MAX_RETRIES + 1} attempts"
        ) from last_exc

    async def _stream_step_once(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        url = f"{self.base_url}/v1/messages"
        # Use a non-streaming request to inspect status, then stream
        req = self._client.build_request("POST", url, json=body)
        resp = await self._client.send(req, stream=True)
        try:
            if resp.status_code in (401, 403):
                await resp.aclose()
                raise AuthError(f"Auth failed: {resp.status_code}")
            if resp.status_code in _RETRIABLE_STATUS:
                await resp.aclose()
                raise _RetriableError(f"Status {resp.status_code}")
            if resp.status_code == 400:
                # Check for context overflow
                body_bytes = await resp.aread()
                await resp.aclose()
                text = body_bytes.decode("utf-8", errors="replace")
                if "context_length" in text or "too long" in text.lower():
                    raise ContextOverflowError(text)
                raise _RetriableError(f"400: {text[:200]}")
            resp.raise_for_status()

            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            current_block: dict[str, Any] | None = None

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: "):])
                etype = payload.get("type")

                if etype == "content_block_start":
                    current_block = payload["content_block"]
                    if current_block["type"] == "text":
                        current_block.setdefault("text", "")
                    elif current_block["type"] == "tool_use":
                        current_block["input_str"] = ""

                elif etype == "content_block_delta":
                    delta = payload["delta"]
                    if delta["type"] == "text_delta":
                        assert current_block is not None
                        current_block["text"] += delta["text"]
                    elif delta["type"] == "input_json_delta":
                        assert current_block is not None
                        current_block["input_str"] += delta["partial_json"]

                elif etype == "content_block_stop":
                    assert current_block is not None
                    if current_block["type"] == "text":
                        text_parts.append(current_block["text"])
                    elif current_block["type"] == "tool_use":
                        try:
                            input_obj = (
                                json.loads(current_block["input_str"])
                                if current_block["input_str"]
                                else {}
                            )
                        except json.JSONDecodeError:
                            input_obj = {}
                        tool_calls.append(
                            ToolCall(
                                id=current_block["id"],
                                name=current_block["name"],
                                input=input_obj,
                            )
                        )
                    current_block = None

            return "".join(text_parts), tool_calls
        finally:
            if not resp.is_closed:
                await resp.aclose()
