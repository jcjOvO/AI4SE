# TUI 美化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 miniagent TUI 从基础样式升级为 Catppuccin Mocha 暗色主题 + 面板式消息 + token 用量显示 + spinner 状态栏。

**Architecture:** 自底向上——先改 llm.py 捕获 usage，再改 agent.py 透传，最后重写 tui.py 的视觉层。CSS 独立为 tui.css 文件。

**Tech Stack:** Python 3.12, Textual 0.80+, Rich (Panel/Syntax), httpx, pytest

---

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/miniagent/llm.py` | 修改 | 新增 `StepUsage`，SSE 解析捕获 usage |
| `src/miniagent/agent.py` | 修改 | `EndTurn` 加 usage 字段，`run()` 透传 |
| `src/miniagent/tui.css` | 新建 | Catppuccin Mocha 暗色主题 CSS |
| `src/miniagent/tui.py` | 重写 | 面板式消息 + header token 显示 + spinner |
| `tests/unit/test_llm.py` | 修改 | 适配新返回类型 + 验证 usage |
| `tests/unit/test_agent.py` | 修改 | 适配 EndTurn 新字段 + FakeLLM 返回类型 |
| `tests/integration/test_tui.py` | 修改 | 适配新 widget 结构 |

---

## Task 1: llm.py — StepUsage + SSE usage 捕获

**Files:**
- Modify: `src/miniagent/llm.py`
- Test: `tests/unit/test_llm.py`

### Step 1: 写失败测试 — stream_step 返回 usage

在 `tests/unit/test_llm.py` 的 `test_stream_step_returns_text_and_tool_calls` 末尾追加 usage 断言：

```python
    # 现有的断言之后追加:
    # 当前返回 tuple[str, list[ToolCall]]，改为 tuple[str, list[ToolCall], StepUsage]
    assert len(result) == 3
    from miniagent.llm import StepUsage
    usage = result[2]
    assert isinstance(usage, StepUsage)
    assert usage.input_tokens == 5  # 来自 message_start
    assert usage.output_tokens > 0  # 来自 message_delta
```

同时修改解构：

```python
    # 原来: text, tool_calls = await llm.stream_step(...)
    # 改为:
    text, tool_calls, usage = await llm.stream_step(...)
```

### Step 2: 跑测试确认失败

```bash
uv run pytest tests/unit/test_llm.py::test_stream_step_returns_text_and_tool_calls -v
```

预期：FAIL — `StepUsage` 不存在，返回值解构失败。

### Step 3: 实现 StepUsage + 修改 SSE 解析

在 `src/miniagent/llm.py` 中：

**3a.** 在 `ToolCall` dataclass 之后添加 `StepUsage`：

```python
@dataclass
class StepUsage:
    input_tokens: int = 0
    output_tokens: int = 0
```

**3b.** 修改 `_stream_step_once` 方法签名和返回值：

```python
async def _stream_step_once(
    self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> tuple[str, list[ToolCall], StepUsage]:
```

**3c.** 在 `_stream_step_once` 内部，SSE 解析循环之前初始化 usage：

```python
    usage = StepUsage()
```

**3d.** 在 `async for line` 循环中，`if etype == "content_block_start":` 之前添加 usage 捕获：

```python
                if etype == "message_start":
                    msg_usage = payload.get("message", {}).get("usage", {})
                    usage.input_tokens = msg_usage.get("input_tokens", 0)

                elif etype == "message_delta":
                    delta_usage = payload.get("usage", {})
                    usage.output_tokens = delta_usage.get("output_tokens", 0)

                elif etype == "content_block_start":
                    # ... 现有代码
```

注意：原来的 `if etype == "content_block_start":` 改为 `elif`，因为现在有多个 etype 分支。

**3e.** 修改返回值：

```python
            return "".join(text_parts), tool_calls, usage
```

**3f.** 修改 `stream_step` 方法签名：

```python
async def stream_step(
    self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> tuple[str, list[ToolCall], StepUsage]:
```

重试循环中的返回值也同步更新（`_stream_step_once` 的返回直接透传）。

### Step 4: 更新所有解构 `stream_step` 返回值的测试

修改 `tests/unit/test_llm.py` 中所有 `text, _ = await llm.stream_step(...)` 和 `text, tool_calls = await llm.stream_step(...)` 为三元解构：

```python
    text, _, _ = await llm.stream_step(...)
    # 或
    text, tool_calls, usage = await llm.stream_step(...)
```

涉及的测试函数：
- `test_stream_step_returns_text_and_tool_calls` — Step 1 已改
- `test_stream_step_passes_messages_and_model` — `text, _, _`
- `test_retries_on_429_then_succeeds` — `text, _, _`
- `test_no_retry_on_401` — 无需改（raises）
- `test_retry_exhausted_after_4_attempts` — 无需改（raises）

### Step 5: 新增测试 — usage 为 0 的兼容性

```python
@respx.mock
async def test_stream_step_usage_defaults_to_zero_when_missing(llm: LLMClient) -> None:
    """API 未返回 usage 字段时，默认 StepUsage(0, 0)。"""
    events = [
        {
            "type": "message_start",
            "message": {"id": "m", "role": "assistant", "content": [], "stop_reason": "end_turn"},
        },
        {"type": "message_stop"},
    ]
    body = "\n".join(f"event: {e['type']}\ndata: {json.dumps(e)}" for e in events)
    respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )
    _, _, usage = await llm.stream_step(messages=[{"role": "user", "content": "x"}], tools=[])
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
```

### Step 6: 跑全部测试确认通过

```bash
uv run pytest tests/unit/test_llm.py -v
```

预期：全部 PASS。

### Step 7: 提交

```bash
git add src/miniagent/llm.py tests/unit/test_llm.py
git commit -m "feat(llm): capture SSE usage into StepUsage dataclass"
```

---

## Task 2: agent.py — EndTurn 透传 usage

**Files:**
- Modify: `src/miniagent/agent.py`
- Test: `tests/unit/test_agent.py`

### Step 1: 写失败测试 — EndTurn 带 usage 字段

修改 `test_run_emits_assistant_delta_and_end_turn_on_text_only_response`：

```python
async def test_run_emits_assistant_delta_and_end_turn_on_text_only_response() -> None:
    llm = FakeLLM(responses=[("Hi there!", [])])
    tools = FakeTools(by_name={})
    events: list[Event] = []

    msgs = await run(
        messages=[{"role": "user", "content": "hi"}],
        llm=llm,
        tools=tools,
        on_event=events.append,
    )
    assert msgs

    assert len(events) == 2
    assert isinstance(events[0], AssistantDelta)
    assert events[0].text == "Hi there!"
    assert isinstance(events[1], EndTurn)
    assert events[1].final_text == "Hi there!"
    assert events[1].input_tokens == 0  # FakeLLM 不返回 usage
    assert events[1].output_tokens == 0
```

### Step 2: 更新 FakeLLM 返回类型

`FakeLLM.stream_step` 需要返回三元组以匹配新的 `LLMProtocol`：

```python
@dataclass
class FakeLLM:
    """Mimics LLMClient.stream_step; user scripts a queue of responses."""

    responses: list[tuple[str, list[FakeToolCall]]]

    async def stream_step(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[FakeToolCall], Any]:
        text, tool_calls = self.responses.pop(0)
        return text, tool_calls, None  # None = no usage
```

同时修改 `HangingLLM`（在 `test_run_propagates_cancellation` 中）：

```python
    @dataclass
    class HangingLLM:
        async def stream_step(self, messages, tools):
            await asyncio.sleep(10)
            return "", [], None  # pragma: no cover
```

### Step 3: 跑测试确认失败

```bash
uv run pytest tests/unit/test_agent.py::test_run_emits_assistant_delta_and_end_turn_on_text_only_response -v
```

预期：FAIL — `EndTurn` 没有 `input_tokens` 属性。

### Step 4: 修改 agent.py

**4a.** 修改 `EndTurn` dataclass：

```python
@dataclass
class EndTurn:
    final_text: str
    input_tokens: int = 0
    output_tokens: int = 0
```

**4b.** 修改 `LLMProtocol`：

```python
class LLMProtocol(Protocol):
    async def stream_step(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[Any], Any]: ...
```

**4c.** 修改 `run()` 函数中的解构和 EndTurn 构造：

```python
            text, tool_calls, usage = await llm.stream_step(messages, tools.all_schemas())
```

```python
            if not tool_calls:
                input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
                output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
                on_event(EndTurn(
                    final_text=text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ))
                return messages
```

使用 `getattr` + `if usage` 是为了兼容 `FakeLLM` 返回 `None` 和真实 `StepUsage` 两种情况。

### Step 5: 跑全部测试确认通过

```bash
uv run pytest tests/unit/test_agent.py -v
```

预期：全部 PASS。

### Step 6: 提交

```bash
git add src/miniagent/agent.py tests/unit/test_agent.py
git commit -m "feat(agent): pass usage through EndTurn event"
```

---

## Task 3: tui.css — Catppuccin Mocha 暗色主题

**Files:**
- Create: `src/miniagent/tui.css`

### Step 1: 创建 CSS 文件

```css
/* Catppuccin Mocha inspired dark theme for miniagent TUI */

AgentApp {
    background: #1e1e2e;
    color: #cdd6f4;
}

/* ── Header ─────────────────────────────────────────── */

#header {
    dock: top;
    height: 1;
    background: #313244;
    color: #a6adc8;
    padding: 0 1;
}

/* ── Chat Log ───────────────────────────────────────── */

#log {
    height: 1fr;
    border: solid #585b70;
    background: #1e1e2e;
    scrollbar-color: #585b70;
    scrollbar-color-hover: #6c7086;
    scrollbar-color-active: #7f849c;
}

/* ── Status Bar ─────────────────────────────────────── */

#status {
    dock: bottom;
    height: 1;
    background: #313244;
    color: #a6adc8;
    padding: 0 1;
}

/* ── Input ──────────────────────────────────────────── */

#input {
    dock: bottom;
    background: #313244;
    color: #cdd6f4;
    border: solid #585b70;
    padding: 0 1;
}

#input:focus {
    border: solid #89dceb;
}
```

### Step 2: 提交

```bash
git add src/miniagent/tui.css
git commit -m "feat(tui): add Catppuccin Mocha dark theme CSS"
```

---

## Task 4: tui.py — Header + Status Bar + Spinner

**Files:**
- Modify: `src/miniagent/tui.py`
- Test: `tests/integration/test_tui.py`

### Step 1: 写失败测试 — header 显示模型名

修改 `test_app_starts_and_shows_header_and_input`：

```python
@pytest.mark.asyncio
async def test_app_starts_and_shows_header_and_input() -> None:
    app = AgentApp(llm=None, tools=None, session=None, session_id="test-123", model_name="claude-x")  # type: ignore[arg-type]
    async with app.run_test() as pilot:
        header = app.query_one("#header", Static)
        header_text = str(header.renderable)
        assert "miniagent" in header_text
        assert "claude-x" in header_text
        assert "test-123" in header_text
        # 右侧应显示 ready（无 token 数据时）
        assert "ready" in header_text
        # Status bar 存在
        status = app.query_one("#status", Static)
        assert status is not None
        # Input 存在
        assert app.query_one(Input) is not None
        await pilot.pause()
```

### Step 2: 写失败测试 — spinner 状态切换

```python
@pytest.mark.asyncio
async def test_status_bar_shows_thinking_during_agent_run() -> None:
    """Status bar 应在 agent 运行时显示 thinking 状态。"""
    import asyncio

    @dataclass
    class SlowLLM:
        async def stream_step(self, messages, tools):
            await asyncio.sleep(0.2)
            return "done", [], None

    app = AgentApp(
        llm=SlowLLM(),  # type: ignore[arg-type]
        tools=_Tools(),  # type: ignore[arg-type]
        session=None,
        session_id="s-spinner",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("h", "i", "enter")
        await pilot.pause()  # 让 agent 开始
        status = app.query_one("#status", Static)
        status_text = str(status.renderable)
        # 应包含 thinking 或 calling 状态
        assert "thinking" in status_text or "calling" in status_text or "⠋" in status_text or "⠹" in status_text
```

### Step 3: 跑测试确认失败

```bash
uv run pytest tests/integration/test_tui.py::test_app_starts_and_shows_header_and_input -v
```

预期：FAIL — header 内容不匹配。

### Step 4: 重写 tui.py — Header + Status Bar + Spinner

完整重写 `src/miniagent/tui.py`：

```python
"""Textual TUI app."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from miniagent.agent import (
    AgentError,
    AssistantDelta,
    EndTurn,
    Event,
    ToolCallResult,
    ToolCallStart,
)
from miniagent.agent import (
    run as agent_run,
)

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_CSS_PATH = Path(__file__).parent / "tui.css"


class AgentApp(App[None]):
    """Single-panel TUI: header / scrollable log / status / input."""

    CSS_PATH = _CSS_PATH

    def __init__(
        self,
        llm: Any,
        tools: Any,
        session: Any,
        session_id: str,
        model_name: str = "claude-x",
        initial_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.llm = llm
        self.tools = tools
        self.session = session
        self.session_id = session_id
        self.model_name = model_name
        self._messages: list[dict[str, Any]] = list(initial_messages or [])
        self._busy: bool = False
        self._turn_start: float = 0.0
        self._total_input: int = 0
        self._total_output: int = 0
        self._spinner_idx: int = 0
        self._spinner_timer: Any = None

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header")
        yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Static("ready", id="status")
        yield Input(placeholder="Type a message and press Enter…", id="input")

    def on_mount(self) -> None:
        if hasattr(self.session, "start"):
            self.session.start()
        self.query_one("#input", Input).focus()
        log = self.query_one(RichLog)
        log.write("[bold]Welcome to miniagent. Type a message to begin.[/bold]")
        for msg in self._messages:
            self._replay_message(msg)

    def _header_text(self, right: str = "ready") -> str:
        left = f"● miniagent · {self.model_name} · {self.session_id[:8]}"
        # Pad to fill width — approximate, Textual reflows anyway
        return f" {left}    {right}"

    def _update_header(self, right: str) -> None:
        self.query_one("#header", Static).update(self._header_text(right))

    def _update_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _start_spinner(self, status_text: str) -> None:
        """Start braille spinner with given status prefix."""
        self._spinner_idx = 0
        self._update_status(f"{_SPINNER_FRAMES[0]} {status_text}")

        def tick() -> None:
            self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
            frame = _SPINNER_FRAMES[self._spinner_idx]
            self._update_status(f"{frame} {status_text}")

        self._spinner_timer = self.set_interval(0.08, tick)

    def _stop_spinner(self, final_status: str = "ready") -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._update_status(final_status)

    def _format_tokens(self, inp: int, out: int) -> str:
        def _fmt(n: int) -> str:
            if n >= 1000:
                return f"{n / 1000:.1f}k"
            return str(n)

        return f"tokens: {_fmt(inp)} / {_fmt(out)}"

    def _replay_message(self, msg: dict[str, Any]) -> None:
        log = self.query_one(RichLog)
        content = msg.get("content", "")
        if isinstance(content, str):
            if msg.get("role") == "user":
                log.write(f"[bold cyan]you>[/bold cyan] {content}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    log.write(f"[bold green]assistant>[/bold green] {block.get('text', '')}")
                elif btype == "tool_use":
                    log.write(f"  [magenta]🔧 {block.get('name')}({block.get('input')})[/magenta]")
                elif btype == "tool_result":
                    payload = block.get("content", "")
                    ok = not block.get("is_error", False)
                    mark = "✓" if ok else "✗"
                    color = "green" if ok else "red"
                    log.write(f"  [{color}]{mark} {payload}[/{color}]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._busy:
            return
        text = event.value.strip()
        if not text:
            return
        if text == "/exit":
            self.exit()
            return
        if text == "/reset":
            self._messages.clear()
            self._total_input = 0
            self._total_output = 0
            self._update_header("ready")
            self.query_one(RichLog).write("[italic]Session reset (history cleared)[/italic]")
            self.query_one("#input", Input).value = ""
            return

        log = self.query_one(RichLog)
        log.write(f"[bold cyan]you>[/bold cyan] {text}")
        self.query_one("#input", Input).value = ""
        self._busy = True
        self._turn_start = time.monotonic()
        self._start_spinner("thinking...")

        asyncio.create_task(self._run_agent(text))

    async def _run_agent(self, user_text: str) -> None:
        user_msg: dict[str, Any] = {"role": "user", "content": user_text}
        self._messages.append(user_msg)
        if self.session and self.session_id:
            self.session.append_message(self.session_id, user_msg)

        def emit(event: Event) -> None:
            self._render_event(event)

        try:
            await agent_run(
                messages=self._messages,
                llm=self.llm,
                tools=self.tools,
                on_event=emit,
                session=self.session,
                session_id=self.session_id,
            )
        except asyncio.CancelledError:
            self.query_one(RichLog).write("[yellow]interrupted[/yellow]")
            self._stop_spinner("interrupted")
        except Exception as e:
            self.query_one(RichLog).write(f"[red]error: {e}[/red]")
            self._stop_spinner("error")
        else:
            self._stop_spinner("ready")
        finally:
            self._busy = False

    def _render_event(self, event: Event) -> None:
        log = self.query_one(RichLog)
        if isinstance(event, AssistantDelta):
            log.write(f"[bold green]assistant>[/bold green] {event.text}")
        elif isinstance(event, ToolCallStart):
            self._stop_spinner()
            self._start_spinner(f"calling {event.name}...")
            log.write(f"  [magenta]🔧 {event.name}({event.args})[/magenta]")
        elif isinstance(event, ToolCallResult):
            self._stop_spinner()
            self._start_spinner("thinking...")
            mark = "✓" if event.ok else "✗"
            color = "green" if event.ok else "red"
            payload = event.output if event.ok else (event.error or "")
            log.write(f"  [{color}]{mark} {payload}[/{color}]")
        elif isinstance(event, EndTurn):
            elapsed = time.monotonic() - self._turn_start if self._turn_start else 0
            self._total_input += event.input_tokens
            self._total_output += event.output_tokens
            right = f"{self._format_tokens(self._total_input, self._total_output)} · {elapsed:.1f}s"
            self._update_header(right)
            log.write("")
        elif isinstance(event, AgentError):
            log.write(f"[red]agent error: {event.message}[/red]")
```

### Step 5: 更新测试适配新结构

修改 `tests/integration/test_tui.py` 中的 `_LLM` mock 返回三元组：

```python
@dataclass
class _LLM:
    async def stream_step(self, messages, tools):
        last = messages[-1]
        content = last.get("content", "") if isinstance(last.get("content"), str) else "hi"
        return "Echo: " + content, [], None
```

修改 `test_user_input_triggers_agent_run` 中的 status 断言（spinner 可能还在 "ready" 状态）：

```python
        # Status bar should return to 'ready' after the agent finishes
        status = app.query_one("#status", Static)
        status_text = str(status.renderable)
        assert "ready" in status_text or status_text == "ready"
```

### Step 6: 跑全部测试确认通过

```bash
uv run pytest tests/integration/test_tui.py -v
```

预期：全部 PASS。

### Step 7: 提交

```bash
git add src/miniagent/tui.py src/miniagent/tui.css tests/integration/test_tui.py
git commit -m "feat(tui): header with tokens, spinner status bar, dark theme CSS"
```

---

## Task 5: tui.py — 面板式消息渲染

**Files:**
- Modify: `src/miniagent/tui.py`
- Test: `tests/integration/test_tui.py`

### Step 1: 写失败测试 — 消息用 Panel 渲染

```python
@pytest.mark.asyncio
async def test_messages_rendered_with_panels() -> None:
    """用户和助手消息应使用 Rich Panel 包裹。"""
    app = AgentApp(
        llm=_LLM(),  # type: ignore[arg-type]
        tools=_Tools(),  # type: ignore[arg-type]
        session=None,
        session_id="s-panel",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t", "e", "s", "t", "enter")
        for _ in range(20):
            await pilot.pause()
            log = app.query_one("#log", RichLog)
            text = "\n".join(str(line) for line in log.lines)
            if "Echo: test" in text:
                break
        else:
            pytest.fail(f"Agent response never appeared. Log was:\n{text}")
        # 面板标题应出现
        assert "you" in text
        assert "assistant" in text
```

### Step 2: 跑测试确认失败

```bash
uv run pytest tests/integration/test_tui.py::test_messages_rendered_with_panels -v
```

预期：FAIL — 当前渲染没有 Panel 标题。

### Step 3: 修改 tui.py — 导入 Rich Panel + Syntax

在 `tui.py` 顶部添加导入：

```python
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
```

### Step 4: 重写 `_render_event` 使用 Panel

替换 `_render_event` 方法：

```python
    def _render_event(self, event: Event) -> None:
        log = self.query_one(RichLog)
        if isinstance(event, AssistantDelta):
            panel = Panel(
                event.text,
                title="[bold green]assistant[/bold green]",
                border_style="green",
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, ToolCallStart):
            self._stop_spinner()
            self._start_spinner(f"calling {event.name}...")
            import json as _json
            args_str = _json.dumps(event.args, ensure_ascii=False)
            panel = Panel(
                f"[dim]{args_str}[/dim]",
                title=f"[bold magenta]🔧 {event.name}[/bold magenta]",
                border_style="magenta",
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, ToolCallResult):
            self._stop_spinner()
            self._start_spinner("thinking...")
            mark = "✓" if event.ok else "✗"
            color = "green" if event.ok else "red"
            payload = event.output if event.ok else (event.error or "")
            # 折叠超过 5 行的输出
            lines = payload.split("\n")
            if len(lines) > 5:
                payload = "\n".join(lines[:3]) + f"\n[dim][... {len(lines) - 3} more lines][/dim]"
            panel = Panel(
                f"[{color}]{mark}[/{color}] {payload}",
                border_style=color,
                expand=True,
            )
            log.write(panel)
        elif isinstance(event, EndTurn):
            elapsed = time.monotonic() - self._turn_start if self._turn_start else 0
            self._total_input += event.input_tokens
            self._total_output += event.output_tokens
            right = f"{self._format_tokens(self._total_input, self._total_output)} · {elapsed:.1f}s"
            self._update_header(right)
        elif isinstance(event, AgentError):
            log.write(f"[red]agent error: {event.message}[/red]")
```

### Step 5: 重写 `_replay_message` 使用 Panel

```python
    def _replay_message(self, msg: dict[str, Any]) -> None:
        log = self.query_one(RichLog)
        content = msg.get("content", "")
        if isinstance(content, str):
            if msg.get("role") == "user":
                panel = Panel(
                    content,
                    title="[bold cyan]you[/bold cyan]",
                    border_style="cyan",
                    expand=True,
                )
                log.write(panel)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    panel = Panel(
                        block.get("text", ""),
                        title="[bold green]assistant[/bold green]",
                        border_style="green",
                        expand=True,
                    )
                    log.write(panel)
                elif btype == "tool_use":
                    import json as _json
                    args_str = _json.dumps(block.get("input", {}), ensure_ascii=False)
                    panel = Panel(
                        f"[dim]{args_str}[/dim]",
                        title=f"[bold magenta]🔧 {block.get('name')}[/bold magenta]",
                        border_style="magenta",
                        expand=True,
                    )
                    log.write(panel)
                elif btype == "tool_result":
                    payload = block.get("content", "")
                    ok = not block.get("is_error", False)
                    mark = "✓" if ok else "✗"
                    color = "green" if ok else "red"
                    panel = Panel(
                        f"[{color}]{mark}[/{color}] {payload}",
                        border_style=color,
                        expand=True,
                    )
                    log.write(panel)
```

### Step 6: 修改 `on_input_submitted` 中的用户消息也用 Panel

```python
        log = self.query_one(RichLog)
        panel = Panel(
            text,
            title="[bold cyan]you[/bold cyan]",
            border_style="cyan",
            expand=True,
        )
        log.write(panel)
```

### Step 7: 跑全部测试确认通过

```bash
uv run pytest tests/integration/test_tui.py -v
```

预期：全部 PASS。

### Step 8: 提交

```bash
git add src/miniagent/tui.py tests/integration/test_tui.py
git commit -m "feat(tui): panel-based message rendering with Rich Panel"
```

---

## Task 6: 收尾 — 全量测试 + lint + type

### Step 1: 跑全量测试

```bash
make test
```

预期：全部 PASS（原有 54 tests + 新增 tests）。

### Step 2: Lint 检查

```bash
make lint
```

预期：0 errors。

### Step 3: 类型检查

```bash
make type
```

预期：0 errors。

### Step 4: 手动验证

```bash
uv run miniagent
```

确认：
- Header 显示模型名 + session ID + 右侧 token/耗时
- 消息用 Panel 包裹，颜色正确
- Status bar 有 spinner 动画
- 暗色主题生效

### Step 5: 更新 mock server 的 message_delta 事件（可选）

`scripts/mock_anthropic.py` 的 `message_delta` 事件当前没有 `usage` 字段。e2e 测试不会失败（`StepUsage` 默认 0），但为了完整性可以加上：

```python
'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
'"usage":{"output_tokens":5}}\n\n',
```

### Step 6: 最终提交（如有 lint/type 修复）

```bash
git add -A
git commit -m "style: lint + type fixes for TUI beautification"
```
