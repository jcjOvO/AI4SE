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


@dataclass
class StepUsage:
    input_tokens: int = 0
    output_tokens: int = 0


_RETRIABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
_MAX_RETRIES = 3
# Exponential-backoff base, in seconds. Production should use 1.0s so the
# 429/5xx/529 retries don't hammer the API; tests can set the env var
# `MINI_AGENT_LLM_BACKOFF_BASE=0.01` (or monkeypatch this constant) to
# keep test suites fast. Default 1.0 follows Anthropic's published
# guidance to respect `retry-after` headers.
_BACKOFF_BASE = float(os.environ.get("MINI_AGENT_LLM_BACKOFF_BASE", "1.0"))


def _build_system_prompt(config: Any = None) -> str:
    """Build the system prompt with tool descriptions, safety rules, and response style."""
    from miniagent.tools import tools

    sections: list[str] = []

    # 1. Identity + tool descriptions (dynamic from registry)
    tool_lines: list[str] = []
    for schema in tools.all_schemas():
        name = schema.get("name", "unknown")
        desc = schema.get("description", "No description.")
        tool_lines.append(f"- {name}: {desc}")

    sections.append(
        "You are a coding assistant running in a Docker container.\n"
        "Your working directory is /workspace. "
        "All file operations should be relative to this directory.\n\n"
        "You have the following tools available:\n\n" + "\n".join(tool_lines) + "\n\n"
        "Use tools whenever the user asks you to perform file operations "
        "or run commands.\n"
        "Do NOT describe what you would do — "
        "actually do it by calling the appropriate tool."
    )

    # 2. Safety rules
    sections.append(
        "## Safety Rules\n"
        "- All file paths MUST resolve inside /workspace. "
        "Do not access files outside this directory.\n"
        "- Do NOT execute destructive commands "
        "(rm -rf /, dd, mkfs, etc.).\n"
        "- Do NOT modify system files or install packages "
        "without explicit user request.\n"
        "- If a requested operation violates these rules, "
        "explain why and suggest alternatives."
    )

    # 3. Response style
    sections.append(
        "## Response Style\n"
        "- Reply in Chinese (中文).\n"
        "- Be concise and direct — avoid unnecessary preambles.\n"
        "- When modifying code, explain WHY the change is needed, "
        "not just WHAT changes.\n"
        "- If there are multiple approaches, "
        "list pros/cons and let the user choose."
    )

    result = "\n\n".join(sections)

    # 4. User custom appendix (from config.toml [agent] system_prompt)
    if config and getattr(config, "system_prompt", ""):
        result += "\n\n---\n\n" + config.system_prompt

    return result


class _RetriableError(Exception):
    """Internal marker for errors that should trigger backoff + retry."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        config: Any = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._config = config
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
    ) -> tuple[str, list[ToolCall], StepUsage]:
        """One assistant turn with retry on transient errors."""
        last_exc: Exception | None = None
        attempts_detail: list[str] = []
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._stream_step_once(messages, tools)
            except (AuthError, ContextOverflowError):
                # Non-retriable: propagate immediately
                raise
            except _RetriableError as e:
                last_exc = e
                attempt_info = f"Attempt {attempt + 1}: {e}"
                if e.response_body:
                    attempt_info += f" | Body: {e.response_body[:200]}"
                attempts_detail.append(attempt_info)
            except httpx.TimeoutException as e:
                last_exc = e
                attempts_detail.append(f"Attempt {attempt + 1}: Timeout - {type(e).__name__}: {e}")
            except httpx.ConnectError as e:
                last_exc = e
                attempts_detail.append(f"Attempt {attempt + 1}: Connection error - {e}")
            except Exception as e:
                last_exc = e
                err_type = type(e).__name__
                attempts_detail.append(f"Attempt {attempt + 1}: Unexpected - {err_type}: {e}")
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
                continue
            break
        detail_str = "\n".join(attempts_detail)
        raise RetryExhaustedError(
            f"Exhausted {_MAX_RETRIES + 1} attempts.\n{detail_str}"
        ) from last_exc

    async def _stream_step_once(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall], StepUsage]:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "system": _build_system_prompt(self._config),
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
                body_bytes = await resp.aread()
                await resp.aclose()
                body_text = body_bytes.decode("utf-8", errors="replace")[:500]
                raise _RetriableError(
                    f"Status {resp.status_code}",
                    status_code=resp.status_code,
                    response_body=body_text,
                )
            if resp.status_code == 400:
                # Check for context overflow
                body_bytes = await resp.aread()
                await resp.aclose()
                text = body_bytes.decode("utf-8", errors="replace")
                if "context_length" in text or "too long" in text.lower():
                    raise ContextOverflowError(text)
                raise _RetriableError(
                    f"400: {text[:300]}",
                    status_code=400,
                    response_body=text[:500],
                )
            resp.raise_for_status()

            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            current_block: dict[str, Any] | None = None
            usage = StepUsage()

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: ") :])
                etype = payload.get("type")

                if etype == "message_start":
                    msg_usage = payload.get("message", {}).get("usage", {})
                    usage.input_tokens = msg_usage.get("input_tokens", 0)

                elif etype == "message_delta":
                    delta_usage = payload.get("usage", {})
                    usage.output_tokens = delta_usage.get("output_tokens", 0)

                elif etype == "content_block_start":
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

            return "".join(text_parts), tool_calls, usage
        finally:
            if not resp.is_closed:
                await resp.aclose()
