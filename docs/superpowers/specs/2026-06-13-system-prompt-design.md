# System Prompt 设计文档

**日期**: 2026-06-13
**状态**: Draft
**范围**: 为 Mini Coding Agent TUI 添加结构化 system prompt

---

## 1. 问题陈述

当前 `llm.py:93` 的 `_build_system_prompt()` 返回一个静态的、无工具说明的通用 prompt：

```python
def _build_system_prompt() -> str:
    return (
        "You are a helpful coding assistant running in a terminal. "
        "You have access to tools for reading, writing, and editing files, "
        "as well as executing bash commands. "
        "Always use tools when the user asks you to perform file operations or run commands. "
        "Be concise and direct in your responses."
    )
```

问题：
- 没有告知 LLM 有哪些工具可用、每个工具的用途和参数
- 没有安全边界约束（如限制在 /workspace 内）
- 没有回复风格规范（如中文回复、简洁直接）
- `config.toml` 的 `[agent] system_prompt` 字段存在但从未使用

## 2. 设计目标

1. **默认 prompt 包含三部分内容**：工具使用说明、安全边界约束、回复风格
2. **工具说明动态注入**：从 `tools.all_schemas()` 自动获取，不硬编码工具名
3. **Config 可追加**：`config.toml` 的 `system_prompt` 字段内容拼接到默认 prompt 后面
4. **最小改动**：不新增模块，不改 agent 循环

## 3. System Prompt 结构

```
[身份 + 工具说明]  ← 动态生成，包含 tools.all_schemas() 的描述
[安全边界约束]     ← 硬编码
[回复风格]         ← 硬编码
---                ← 分隔线（仅当用户自定义存在时）
[用户自定义]       ← 来自 config.toml 的 system_prompt 字段
```

### 3.1 身份 + 工具说明

```text
You are a coding assistant running in a Docker container.
Your working directory is /workspace. All file operations should be relative to this directory.

You have the following tools available:

- read_file: Read the contents of a file at the given path.
- write_file: Write content to a file at the given path. Creates parent directories if needed.
- edit_file: Replace exact text in a file. Use this for targeted changes.
- bash: Execute a shell command and return its output.

Use tools whenever the user asks you to perform file operations or run commands.
Do NOT describe what you would do — actually do it by calling the appropriate tool.
```

工具列表从 `tools.all_schemas()` 动态读取，格式为 `- name: description`。

### 3.2 安全边界约束

```text
## Safety Rules
- All file paths MUST resolve inside /workspace. Do not access files outside this directory.
- Do NOT execute destructive commands (rm -rf /, dd, mkfs, etc.).
- Do NOT modify system files or install packages without explicit user request.
- If a requested operation violates these rules, explain why and suggest alternatives.
```

### 3.3 回复风格

```text
## Response Style
- Reply in Chinese (中文).
- Be concise and direct — avoid unnecessary preambles.
- When modifying code, explain WHY the change is needed, not just WHAT changes.
- If there are multiple approaches, list pros/cons and let the user choose.
```

### 3.4 用户自定义追加

当 `config.toml` 的 `[agent] system_prompt` 非空时，追加：

```text
---
{user_custom_content}
```

## 4. 代码改动

### 4.1 `src/miniagent/config.py`

`AgentConfig` 添加 `system_prompt` 字段：

```python
class AgentConfig(BaseModel):
    max_turns: int = 100
    system_prompt: str = ""  # 用户自定义部分，追加到默认 prompt 后
```

### 4.2 `src/miniagent/llm.py`

重写 `_build_system_prompt()`：

```python
def _build_system_prompt(config: AgentConfig | None = None) -> str:
    from miniagent.tools import tools

    sections = []

    # 1. 身份 + 工具说明
    tool_lines = []
    for schema in tools.all_schemas():
        name = schema.get("name", "unknown")
        desc = schema.get("description", "No description.")
        tool_lines.append(f"- {name}: {desc}")

    sections.append(
        "You are a coding assistant running in a Docker container.\n"
        "Your working directory is /workspace. All file operations should be relative to this directory.\n\n"
        "You have the following tools available:\n\n"
        + "\n".join(tool_lines)
        + "\n\n"
        "Use tools whenever the user asks you to perform file operations or run commands.\n"
        "Do NOT describe what you would do — actually do it by calling the appropriate tool."
    )

    # 2. 安全边界约束
    sections.append(
        "## Safety Rules\n"
        "- All file paths MUST resolve inside /workspace. Do not access files outside this directory.\n"
        "- Do NOT execute destructive commands (rm -rf /, dd, mkfs, etc.).\n"
        "- Do NOT modify system files or install packages without explicit user request.\n"
        "- If a requested operation violates these rules, explain why and suggest alternatives."
    )

    # 3. 回复风格
    sections.append(
        "## Response Style\n"
        "- Reply in Chinese (中文).\n"
        "- Be concise and direct — avoid unnecessary preambles.\n"
        "- When modifying code, explain WHY the change is needed, not just WHAT changes.\n"
        "- If there are multiple approaches, list pros/cons and let the user choose."
    )

    result = "\n\n".join(sections)

    # 4. 用户自定义追加
    if config and config.system_prompt:
        result += "\n\n---\n\n" + config.system_prompt

    return result
```

`stream_chat()` 方法签名不变，但内部调用时传入 config：

```python
async def stream_chat(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    system: str | None = None,  # 如果传入则覆盖默认
) -> AsyncGenerator[LLMEvent, None]:
    # ...
    system_prompt = system if system is not None else _build_system_prompt(self._config)
```

注意：`LLMClient.__init__` 需要接收并存储 `config`。

### 4.3 `src/miniagent/agent.py`

**无需改动**。agent 循环调用 `stream_chat()` 时不传 `system` 参数，`llm.py` 内部自动使用 `_build_system_prompt(config)`。

## 5. 不做的事情

- ❌ 不新增模块（不创建 `system_prompt.py`）
- ❌ 不改 agent 循环
- ❌ 不支持运行时动态修改 system prompt
- ❌ 不在 system prompt 中注入完整的工具 JSON schema（只注入名称和描述）
- ❌ 不做 prompt 模板引擎（简单字符串拼接）

## 6. 测试策略

1. **单元测试**：`test_llm.py` 中添加测试
   - `_build_system_prompt()` 包含工具名称
   - `_build_system_prompt()` 包含安全约束关键词
   - `_build_system_prompt()` 包含回复风格关键词
   - `_build_system_prompt(config_with_custom)` 包含自定义内容
   - `_build_system_prompt(config_empty)` 不包含分隔线

2. **集成测试**：验证 `LLMClient.stream_chat()` 使用新的 system prompt
