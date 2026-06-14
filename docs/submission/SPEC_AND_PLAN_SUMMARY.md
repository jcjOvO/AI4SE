# SPEC + PLAN 汇总

> 本文档汇总 [SPEC](../superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md)（494 行）和 [PLAN](../superpowers/plans/2026-06-01-mini-coding-agent-tui.md)（3210 行）的核心内容。

---

## 一、问题陈述

**Mini Coding Agent TUI** 提供一个**单二进制（Docker 镜像）开箱即用**的终端形态方案：在项目根目录下一条命令 `docker run -it ...` 即可进入一个**多工具、多轮、流式输出**的 agent 会话，无需订阅、无需 IDE 插件、无需后端服务。

**目标用户**：
- 个人开发者，在自己的小项目里跑 agent 做"杂活"
- 学习者：想看清一个最小可用的 coding agent 内部是怎么运转的
- 课程场景下的演示者：能在一台干净的 Linux 机器上 `docker run` 立刻跑起来

**价值**：30 秒内能讲清——"在终端里让 Claude 帮你改代码，BYOK，单 Docker 镜像即跑"

---

## 二、用户故事（5 个）

1. **首次启动**：用户 `make run` → TUI 启动 → 在面板里看到欢迎语与输入提示
2. **单次问答**：用户输入"解释 main.py 做什么" → agent 调 `read_file` + 可选 `bash` → 流式输出解释
3. **修改代码**：用户输入"给 main.py 加上 docstring" → agent 调 `read_file` → `edit_file` → 用户在面板里看到工具调用记录与新内容
4. **跨 session 续接**：用户 Ctrl+C 退出 → 重新 `make run --resume <id>` → 历史对话完整恢复
5. **配置切换**：用户改 config.toml 的 model 字段 → 下次启动自动用新模型，无需改代码

---

## 三、功能规约（6 个模块）

### 3.1 模块 F1：配置（`config`）

- **输入**：`~/.config/mini-agent/config.toml`（用户级） + `./.mini-agent.toml`（项目级） + CLI 参数
- **行为**：Pydantic 校验、fail-fast 报错
- **错误处理**：缺 `api_key` → 启动失败并打印指引

### 3.2 模块 F2：LLM 客户端（`llm`）

- **行为**：调用 Anthropic Messages API，流式接收 SSE，累积 `(text, tool_calls)`
- **错误处理**：
  - `401/403`：不重试，抛 `AuthError`
  - `429/5xx/529`：指数退避重试 3 次
  - `context_length_exceeded`：抛 `ContextOverflowError`

### 3.3 模块 F3：工具集（`tools`）

| 工具 | 输入 | 输出 | 错误 |
|------|------|------|------|
| `read_file` | `path`, `offset`, `limit` | 文件内容 | FileNotFound / IsADirectory |
| `write_file` | `path`, `content` | "Wrote N bytes" | 权限错误 |
| `edit_file` | `path`, `old_string`, `new_string`, `replace_all` | "Edited N replacements" | not found / not unique |
| `bash` | `command`, `timeout` | stdout + stderr + exit code | Path escapes sandbox |

**安全边界**：所有文件工具拒绝跳出 `/workspace` 的请求

### 3.4 模块 F4：Agent 循环（`agent`）

- **行为**：`while True` 循环——调 LLM → 有 tool_calls 则执行并回流结果 → 无 tool_calls 则返回
- **错误处理**：
  - 工具返回 `is_error=True`：不中断，回传 LLM
  - 用户中断：`CancelledError` 透传
  - 编程异常：包成 `AgentError` 推给 TUI

### 3.5 模块 F5：会话持久化（`session`）

- **存储**：SQLite 单文件
- **API**：`create()` / `get()` / `list_recent()` / `append_message()` / `load_messages()`
- **行为**：写入走 `asyncio.Queue` 异步 flush

### 3.6 模块 F6：TUI（`tui`）

- **框架**：Textual
- **布局**：Header + RichLog + Input + StatusBar
- **交互**：Enter 提交 / Ctrl+C 中断 / `/reset` 软重置 / `/exit` 退出

---

## 四、系统架构

```
┌──────────────┐    user input    ┌──────────────────┐
│   TUI        │ ────────────────▶│     Agent        │
│  (Textual)   │                  │   (async loop)   │
│              │ ◀──── events ─── │                  │
└──────────────┘                  └────────┬─────────┘
                                           │
                            ┌──────────────┼──────────────┐
                            ▼              ▼              ▼
                       ┌────────┐    ┌────────┐    ┌──────────────┐
                       │  LLM   │    │ Tools  │    │  Session     │
                       │ client │    │ (4个)  │    │ (SQLite 辅助)│
                       └────────┘    └────────┘    └──────────────┘
                            │
                            ▼
                  Anthropic Messages API
                  (BYOK, base_url 可指向代理)
```

**5 个核心功能模块**（`config` / `llm` / `tools` / `agent` / `tui`）+ 1 个**持久化辅助层**（`session`）

---

## 五、数据模型

### 5.1 核心类型

```python
# Events
AssistantDelta:    text: str
ToolCallStart:     call_id: str; name: str; args: dict
ToolCallResult:    call_id: str; ok: bool; output: str; error: str | None
EndTurn:           final_text: str
AgentError:        message: str; recoverable: bool

# Tool
Tool:  name / description / input_schema / handler
ToolResult:  output / error / is_error

# Config (Pydantic)
Config:  llm (LLMConfig) / paths (PathsConfig) / agent (AgentConfig)
```

### 5.2 Session Schema

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, title TEXT, created_at REAL, updated_at REAL
);
CREATE TABLE messages (
    session_id TEXT REFERENCES sessions(id), seq INTEGER,
    role TEXT, content TEXT, created_at REAL,
    PRIMARY KEY (session_id, seq)
);
```

---

## 六、API 设计（模块间接口）

```python
# config.py
def load_config(cli_overrides: dict | None = None) -> Config

# llm.py
class LLMClient:
    async def stream_step(messages, tools) -> tuple[str, list[ToolCall]]

# tools.py
REGISTRY: dict[str, Tool]
async def execute(name, args) -> ToolResult
def all_schemas() -> list[dict]

# agent.py
async def run(messages, llm, tools, on_event, session, session_id) -> list[dict]

# session.py
class SessionStore:  # sync CRUD
class AsyncSessionStore:  # non-blocking wrapper

# CLI
miniagent [--resume ID] [--list] [--model MODEL] [--config PATH]
```

---

## 七、技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12 | 生态成熟、Textual 流畅 |
| TUI | Textual | 现代、异步、CSS-like 样式 |
| LLM SDK | 直调 anthropic SDK | 零抽象、~30 行 agent 循环 |
| 配置 | TOML + Pydantic | 嵌套支持 + fail-fast 校验 |
| 持久化 | SQLite | 单文件、ACID、零外部依赖 |
| 沙箱 | Docker 容器 | 容器即天然沙箱 |
| 包管理 | uv | 快 10–100×、lock 保证一致 |
| Lint/Type | ruff + mypy strict | 行业标准 |
| CI | GitHub Actions | 课程默认 |

**未选框架理由**：与"mini 基础"定位冲突；自身 ~30 行已够用

---

## 八、非功能性需求

- **性能**：首 token < 2s、TUI ≥ 30fps、启动 < 3s、单 session ≥ 1000 条消息
- **安全**：非 root 用户、路径越界强制拒绝、API key 不入 session.db
- **可用性**：终端 ≥ 80 字符、支持 256 色、错误信息人类可读
- **可观测**：事件进 session.db、启动打印 session_id、关键事件记 stderr

---

## 九、验收标准

| 模块 | 完成判据 |
|------|---------|
| `config` | 缺字段报错清晰、合法配置加载、CLI 覆盖生效 |
| `llm` | respx 单测覆盖 200/401/429/流式/context overflow |
| `tools` | 4 工具各 ≥5 测试全绿、路径越界测试存在 |
| `agent` | 全循环跑通、Ctrl+C 能恢复 |
| `session` | CRUD 全绿、损坏 DB 抛异常、`--resume` 还原 |
| `tui` | Pilot 集成测试通过 |
| `Docker` | `docker build` 成功、`docker run -it` 能输入 |
| `CI` | `ci.yml` 全绿 |

---

## 十、范围之外（明确不做）

- 多 provider 自动切换、工具权限分级、子 agent / 任务委派
- Web UI / IDE 插件、自动 commit / PR、上下文压缩
- 工具调用人工审批、多用户 / 认证 / 远程访问
- MCP、RAG、记忆系统、语音输入

---

## 十一、风险与应对

| 风险 | 应对 |
|------|------|
| Anthropic 工具 schema 不一致 | 先用固定 prompt + 4 工具跑通 |
| Textual 在容器真 tty 下的输入 | E2E 必须真在 `docker run -it` 里跑 |
| SSE 解析与 SDK 版本耦合 | `uv.lock` 锁定依赖、CI 跑 `uv lock --check` |
| `base_url` 指向非 Anthropic 服务商 | `llm.py` 留 adapter 钩子 |
| SQLite 写锁与事件循环协作 | 后台 flush task + `asyncio.Queue` |

---

## 十二、实现计划（19 个 Task）

| Task | 描述 | 涉及文件 | 测试数 |
|------|------|---------|--------|
| 1 | 项目骨架 + uv + 测试基建 | pyproject.toml / Makefile / conftest | 0 |
| 2 | Config 模块 | config.py | 3 |
| 3 | Tools 骨架 | tools.py | 4 |
| 4 | read_file | tools.py | 5 |
| 5 | write_file | tools.py | 5 |
| 6 | edit_file | tools.py | 5 |
| 7 | bash + 路径检测 | tools.py | 6 |
| 8 | SessionStore (sync) | session.py | 8 |
| 8b | AsyncSessionStore | session.py | 2 |
| 9 | LLMClient skeleton | llm.py | 2 |
| 10 | LLMClient retry | llm.py | 3 |
| 11 | Agent loop | agent.py | 4 |
| 12 | TUI skeleton | tui.py | 1 |
| 13 | TUI wire input → agent | tui.py | 1 |
| 14 | CLI (__main__) | __main__.py | 2 |
| 15 | Dockerfile + compose | Dockerfile | 0 |
| 16 | CI workflows | .github/workflows | 0 |
| 17 | README | README.md | 0 |
| 18 | E2E mock LLM | e2e/ + scripts/ | 1 |
| 19 | AGENT_LOG + plan tick | AGENT_LOG.md | 0 |

**总计**：55 tests（52 unit + 2 integration + 1 e2e）

---

## 十三、并行化策略

| 阶段 | 可并行 Task | 约束 |
|------|------------|------|
| Task 1 后 | Task 2 (config) | — |
| Task 2 后 | Task 3 (tools) + Task 8 (session) | 不同文件 |
| Task 3 后 | Task 4-7 (4 个 tool) | **必须串行**（同文件 tools.py） |
| Task 8 后 | Task 8b + Task 9 | Task 8b 同文件串行、Task 9 不同文件 |
| Task 9+7 后 | Task 10 + Task 11 | 不同文件 |
| Task 11 后 | Task 12 (TUI) | — |
| Task 12 后 | Task 13 (TUI wire) | **同文件串行** |
| Task 13 后 | Task 14 (CLI) | — |
| Task 14 后 | Task 15/16/17 | **3 个并行 worktree** |
| Task 16 后 | Task 18 (E2E) | — |

---

## 十四、目录结构（最终形态）

```
AI4SE/
├── SPEC.md / PLAN.md / SPEC_PROCESS.md / AGENT_LOG.md / REFLECTION.md
├── README.md / pyproject.toml / uv.lock / Makefile
├── Dockerfile / docker-compose.yml
├── .github/workflows/ (ci.yml + e2e.yml)
├── docs/ (课程文档 + superpowers specs/plans)
├── src/miniagent/
│   ├── __init__.py / __main__.py
│   ├── config.py (~150 行)
│   ├── llm.py (~250 行)
│   ├── tools.py (~400 行)
│   ├── agent.py (~200 行)
│   ├── tui.py (~350 行)
│   └── session.py (~250 行)
└── tests/
    ├── conftest.py
    ├── unit/ (5 个 test 文件)
    ├── integration/ (test_tui.py)
    └── e2e/ (test_docker_smoke.py)
```

**总代码量**：src ~1600 行 + tests ~1800 行 = ~3400 行
