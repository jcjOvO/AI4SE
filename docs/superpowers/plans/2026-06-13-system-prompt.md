# System Prompt 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Mini Coding Agent TUI 添加结构化 system prompt，包含工具说明、安全约束、回复风格，并支持 config.toml 追加自定义内容。

**Architecture:** 重写 `llm.py` 的 `_build_system_prompt()` 函数，从 `tools.all_schemas()` 动态注入工具说明，拼接安全约束和回复风格。`LLMClient.__init__` 新增 `config` 参数存储配置，`_stream_step_once` 将 system prompt 注入 API 请求 body。`config.py` 的 `AgentConfig` 添加 `system_prompt` 字段。agent 循环无需改动。

**Tech Stack:** Python 3.12, Pydantic, httpx, pytest, respx

---

## 文件改动清单

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/miniagent/config.py:29-30` | 修改 | `AgentConfig` 添加 `system_prompt: str` 字段 |
| `src/miniagent/llm.py:64-75` | 修改 | `LLMClient.__init__` 接收并存储 `config` |
| `src/miniagent/llm.py:93-99` | 修改 | 重写 `_build_system_prompt(config)` |
| `src/miniagent/llm.py:117-128` | 修改 | `_stream_step_once` 注入 system prompt 到请求 body |
| `src/miniagent/__main__.py:79-83` | 修改 | 创建 `LLMClient` 时传入 `config` |
| `tests/unit/test_llm.py` | 修改 | 添加 system prompt 相关测试 |

---

### Task 1: AgentConfig 添加 system_prompt 字段

**Files:**
- Modify: `src/miniagent/config.py:29-30`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/unit/test_config.py` 中添加测试（如果文件不存在则创建）：

```python
def test_agent_config_system_prompt_default() -> None:
    from miniagent.config import AgentConfig
    cfg = AgentConfig()
    assert cfg.system_prompt == ""


def test_agent_config_system_prompt_custom() -> None:
    from miniagent.config import AgentConfig
    cfg = AgentConfig(system_prompt="Be helpful")
    assert cfg.system_prompt == "Be helpful"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_config.py -v -k "system_prompt"
```

预期：FAIL — `AgentConfig` 没有 `system_prompt` 字段

- [ ] **Step 3: 实现最小代码**

修改 `src/miniagent/config.py:29-30`：

```python
class AgentConfig(BaseModel):
    max_turns: int = 100
    system_prompt: str = ""
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_config.py -v -k "system_prompt"
```

预期：PASS

- [ ] **Step 5: 提交**

```bash
git add src/miniagent/config.py tests/unit/test_config.py
git commit -m "feat(config): add system_prompt field to AgentConfig"
```

---

### Task 2: 重写 _build_system_prompt()

**Files:**
- Modify: `src/miniagent/llm.py:93-99`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/unit/test_llm.py` 末尾添加：

```python
# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------


def test_build_system_prompt_contains_tool_names() -> None:
    from miniagent.llm import _build_system_prompt
    prompt = _build_system_prompt()
    # Should mention all 4 built-in tools
    assert "read_file" in prompt
    assert "write_file" in prompt
    assert "edit_file" in prompt
    assert "bash" in prompt


def test_build_system_prompt_contains_safety_rules() -> None:
    from miniagent.llm import _build_system_prompt
    prompt = _build_system_prompt()
    assert "/workspace" in prompt
    assert "Safety Rules" in prompt


def test_build_system_prompt_contains_response_style() -> None:
    from miniagent.llm import _build_system_prompt
    prompt = _build_system_prompt()
    assert "Response Style" in prompt
    assert "Chinese" in prompt


def test_build_system_prompt_appends_config_custom() -> None:
    from miniagent.config import AgentConfig
    from miniagent.llm import _build_system_prompt
    cfg = AgentConfig(system_prompt="Custom instruction here")
    prompt = _build_system_prompt(cfg)
    assert "Custom instruction here" in prompt
    assert "---" in prompt


def test_build_system_prompt_no_separator_when_empty() -> None:
    from miniagent.config import AgentConfig
    from miniagent.llm import _build_system_prompt
    cfg = AgentConfig(system_prompt="")
    prompt = _build_system_prompt(cfg)
    # The "---" separator should NOT appear when custom is empty
    # Split by sections and check no standalone "---"
    lines = prompt.split("\n")
    assert "---" not in lines


def test_build_system_prompt_default_when_no_config() -> None:
    from miniagent.llm import _build_system_prompt
    prompt = _build_system_prompt(None)
    assert "coding assistant" in prompt
    assert "read_file" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_llm.py -v -k "system_prompt"
```

预期：FAIL — `_build_system_prompt()` 不接受参数，且内容不含工具名

- [ ] **Step 3: 实现最小代码**

替换 `src/miniagent/llm.py:93-99` 的 `_build_system_prompt` 函数：

```python
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
        "You have the following tools available:\n\n"
        + "\n".join(tool_lines)
        + "\n\n"
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_llm.py -v -k "system_prompt"
```

预期：PASS

- [ ] **Step 5: 运行全部测试确认无回归**

```bash
uv run pytest tests/unit/test_llm.py -v
```

预期：全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/miniagent/llm.py tests/unit/test_llm.py
git commit -m "feat(llm): rewrite _build_system_prompt with tool descriptions and safety rules"
```

---

### Task 3: LLMClient 注入 system prompt 到 API 请求

**Files:**
- Modify: `src/miniagent/llm.py:64-75` (constructor)
- Modify: `src/miniagent/llm.py:117-128` (_stream_step_once)
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/unit/test_llm.py` 末尾添加：

```python
@respx.mock
async def test_stream_step_sends_system_prompt() -> None:
    """Verify that the API request body includes a system prompt."""
    from miniagent.config import AgentConfig

    cfg = AgentConfig(system_prompt="Custom instruction")
    client = LLMClient(
        api_key="sk-test",
        base_url="https://api.example.com",
        model="claude-x",
        config=cfg,
    )
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    await client.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    body = json.loads(route.calls.last.request.content.decode())
    assert "system" in body
    assert "coding assistant" in body["system"]
    assert "Custom instruction" in body["system"]


@respx.mock
async def test_stream_step_system_prompt_without_config() -> None:
    """LLMClient without config still gets a default system prompt."""
    client = LLMClient(
        api_key="sk-test",
        base_url="https://api.example.com",
        model="claude-x",
    )
    route = respx.post("https://api.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200, text=_empty_sse(), headers={"content-type": "text/event-stream"}
        )
    )
    await client.stream_step(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
    )
    body = json.loads(route.calls.last.request.content.decode())
    assert "system" in body
    assert "read_file" in body["system"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_llm.py -v -k "system_prompt"
```

预期：FAIL — `LLMClient.__init__` 不接受 `config` 参数，请求 body 中无 `system`

- [ ] **Step 3: 实现最小代码**

修改 `src/miniagent/llm.py:64-75`，`LLMClient.__init__` 添加 `config` 参数：

```python
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
```

修改 `src/miniagent/llm.py` 的 `_stream_step_once` 方法，在 body 构建后注入 system prompt：

```python
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
    # ... rest of the method unchanged
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_llm.py -v -k "system_prompt"
```

预期：PASS

- [ ] **Step 5: 运行全部测试确认无回归**

```bash
uv run pytest tests/unit/test_llm.py -v
```

预期：全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/miniagent/llm.py tests/unit/test_llm.py
git commit -m "feat(llm): inject system prompt into API request body"
```

---

### Task 4: __main__.py 传递 config 给 LLMClient

**Files:**
- Modify: `src/miniagent/__main__.py:79-83`
- Test: 手动验证（集成级别）

- [ ] **Step 1: 实现代码**

修改 `src/miniagent/__main__.py:79-83`：

```python
llm = LLMClient(
    api_key=config.llm.api_key,
    base_url=config.llm.base_url,
    model=config.llm.model,
    config=config.agent,
)
```

- [ ] **Step 2: 运行全部测试确认无回归**

```bash
uv run pytest tests/unit -v
```

预期：全部 PASS

- [ ] **Step 3: Lint + 类型检查**

```bash
make lint && make type
```

预期：无错误

- [ ] **Step 4: 提交**

```bash
git add src/miniagent/__main__.py
git commit -m "feat(main): pass AgentConfig to LLMClient for system prompt"
```

---

### Task 5: 清理 + 最终验证

- [ ] **Step 1: 运行完整测试套件**

```bash
make test
```

预期：全部 PASS

- [ ] **Step 2: Lint + 类型检查**

```bash
make lint && make type
```

预期：无错误

- [ ] **Step 3: 更新 AGENT_LOG.md**

在 AGENT_LOG.md 中添加本次 system prompt 功能的记录条目。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(agent): add structured system prompt with tool descriptions and safety rules"
```
