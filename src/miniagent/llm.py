"""Thin async wrapper around the Anthropic Messages API (streaming)."""
from __future__ import annotations

import json
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
        """One assistant turn: stream SSE, accumulate text + tool_use blocks.

        Returns (text, tool_calls). tool_calls is empty when stop_reason == "end_turn".
        """
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        url = f"{self.base_url}/v1/messages"
        async with self._client.stream("POST", url, json=body) as resp:
            if resp.status_code in (401, 403):
                raise AuthError(f"Auth failed: {resp.status_code}")
            resp.raise_for_status()

            # Accumulate per content-block state
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            current_block: dict[str, Any] | None = None
            stop_reason: str | None = None

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

                elif etype == "message_delta":
                    stop_reason = payload["delta"].get("stop_reason", stop_reason)

        return "".join(text_parts), tool_calls
