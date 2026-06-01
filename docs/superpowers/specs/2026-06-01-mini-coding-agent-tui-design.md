# SPEC: Mini Coding Agent TUI

> *Spec-Driven, Subagent-Built, Human-Owned.*

| 项目 | 值 |
|---|---|
| 设计日期 | 2026-06-01 |
| 作者 | jcjovo（人类） + Superpowers 主 agent（协作） |
| 状态 | 待人工复核（Phase 1 完成、Phase 2 启动前） |
| 关联 | AI4SE 期末项目 / 课程文档 [docs/AI4SE_Final_Project0518.md](../../AI4SE_Final_Project0518.md) |

---

## 1. 问题陈述

### 1.1 要解决什么问题

学习者、爱好者、轻量开发者经常需要在一个本地代码项目里**通过自然语言驱动 agent 完成小规模编码任务**（改 docstring、解释一段逻辑、批量重命名、跑测试）——但市面上可用工具要么门槛高（订阅 Claude Code / Cursor），要么体验割裂（Web Chat + 手动复制回 IDE），要么重量级（Aider、Continue 需要装 VSCode 插件）。

**Mini Coding Agent TUI** 提供一个**单二进制（Docker 镜像）开箱即用**的终端形态方案：在项目根目录下一条命令 `docker run -it ...` 即可进入一个**多工具、多轮、流式输出**的 agent 会话，无需订阅、无需 IDE 插件、无需后端服务。

### 1.2 目标用户

- 个人开发者，在自己的小项目里跑 agent 做"杂活"
- 学习者：想看清一个最小可用的 coding agent 内部是怎么运转的
- 课程场景下的演示者：能在一台干净的 Linux 机器上 `docker run` 立刻跑起来

### 1.3 为什么值得做

- **30 秒内能讲清价值**："在终端里让 Claude 帮你改代码，BYOK，单 Docker 镜像即跑"
- **真问题**：上述"门槛高/体验割裂/重量级"的痛点
- **教学价值**：源码 3000–4000 行，把"agent loop / tool calling / 流式 TUI / 持久化"四件套完整呈现，是 AI4SE 课程的理想载体

---

## 2. 用户故事（INVEST）

1. **首次启动**：用户 `make run` → TUI 启动 → 在面板里看到欢迎语与输入提示。
2. **单次问答**：用户输入"解释 main.py 做什么" → agent 调 `read_file` + 可选 `bash` → 流式输出解释。
3. **修改代码**：用户输入"给 main.py 加上 docstring" → agent 调 `read_file` → `edit_file` → 用户在面板里看到工具调用记录与新内容。
4. **跨 session 续接**：用户 Ctrl+C 退出 → 重新 `make run --resume <id>` → 历史对话完整恢复。
5. **配置切换**：用户改 config.toml 的 model 字段 → 下次启动自动用新模型，无需改代码。

---

## 3. 功能规约

### 3.1 模块 F1：配置（`config`）

- **输入**：`~/.config/mini-agent/config.toml`（用户级） + 可选 `./.mini-agent.toml`（项目级，项目级覆盖用户级） + CLI 参数（最高优先）
- **行为**：Pydantic 校验、必要字段缺失时 fail-fast 报错并打印最小示例
- **输出**：`Config` dataclass 实例，注入到其他模块
- **边界**：`~` 展开到 `Path`；未知字段发出 warning 但不报错（向前兼容）
- **错误处理**：缺 `api_key` → 启动失败并打印一行指引："export ANTHROPIC_API_KEY=sk-ant-..."

### 3.2 模块 F2：LLM 客户端（`llm`）

- **输入**：`api_key` / `base_url` / `model`（来自 config）+ `messages` + `tools`
- **行为**：调用 Anthropic Messages API（支持 Anthropic 协议的服务商，通过 base_url 配置），流式接收 SSE，分块累积出 `(text, tool_calls)` 二元组
- **输出**：`tuple[str, list[ToolCall]]` —— 累积的助手文本 + 完整 tool_use 块列表
- **边界**：流式 token 不会因为单次网络中断丢失整体 message
- **错误处理**：
  - `401/403`：不重试，抛 `AuthError`
  - `429/5xx/529`：指数退避重试 3 次（1s/2s/4s）
  - `context_length_exceeded`：抛 `ContextOverflowError`
  - 重试上限到达：抛 `RetryExhaustedError`

### 3.3 模块 F3：工具集（`tools`）

四个工具，每个签名统一为 `async def handler(args: dict) -> ToolResult`，注册到 `REGISTRY` 字典。

| 工具 | 输入 | 输出 | 边界条件 | 错误 |
|---|---|---|---|---|
| `read_file` | `path: str`, `offset: int = 0`, `limit: int = 2000` | `output: 文件内容` | 文件不存在、空文件、大文件截断、二进制以十六进制预览 | `error: "FileNotFound: <path>"` / `"IsADirectory: <path>"` |
| `write_file` | `path: str`, `content: str` | `output: "Wrote <N> bytes to <path>"` | 自动创建父目录、覆盖确认无（容器即沙箱） | 权限错误 → 透传 OSError |
| `edit_file` | `path: str`, `old_string: str`, `new_string: str`, `replace_all: bool = False` | `output: "Edited <path> (N replacements)"` | `old_string` 必须唯一（除非 `replace_all`）；找不到时**报错而非创建** | `error: "old_string not found"` / `"old_string not unique (N matches)"` |
| `bash` | `command: str`, `timeout: int = 30` | `output: "<stdout>\n[stderr: <stderr>]\n[exit: <code>]"` | 路径越界**拒绝执行**（即使在容器里） | `error: "Path escapes sandbox: <path>"` / 非零 exit_code 在 `output` 而非 `error` |

**关键安全边界**：
- 所有文件工具拒绝路径解析后跳出 `/workspace`（工作目录）的请求
- `bash` 的 `command` 字符串在执行前用 `shlex` 解析检查路径 token，发现越界则 `error` 拒绝

### 3.4 模块 F4：Agent 循环（`agent`）

- **输入**：初始 `messages: list[dict]`、`on_event: Callable[[Event], None]`、`session: Session`（可选）
- **行为**：
  ```python
  async def run(messages, on_event, session=None):
      while True:
          text, tool_calls = await llm.stream_step(messages, tools_schema)
          on_event(AssistantDelta(text))
          if session: session.append_message(assistant_msg)
          if not tool_calls:
              on_event(EndTurn(text))
              return messages
          for call in tool_calls:
              result = await tools.execute(call.name, call.input)
              on_event(ToolCallResult(call, result))
              if session: session.append_message(tool_result_msg)
              messages.append(tool_result_msg)
  ```
- **边界**：唯一退出路径是 `end_turn`（LLM 返回无 tool_use）或用户 `Ctrl+C` 或不可恢复错误
- **错误处理**：
  - 工具返回 `is_error=True`：不中断循环，把 error 字段作为 `tool_result` 回传 LLM
  - 用户中断：`asyncio.CancelledError` 被捕获，保存当前 messages 到 session 后退出
  - 编程异常：包成 `AgentError(recoverable=False)` 推给 TUI

### 3.5 模块 F5：会话持久化（`session`）

- **存储**：`~/.local/share/mini-agent/sessions.db`（单 SQLite 文件）
- **Schema**：
  ```sql
  CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
  );
  CREATE TABLE messages (
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
  );
  CREATE INDEX idx_messages_session ON messages(session_id, seq);
  ```
- **API**：
  - `create() -> Session`：生成 UUID v4，写入 sessions 行
  - `get(id) -> Session` / `list_recent(limit=20) -> list[SessionMeta]`
  - `append_message(sid, msg) -> None`
  - `load_messages(sid) -> list[dict]`
- **行为**：写入走后台 task 异步 flush（基于 `asyncio.Queue` 缓冲），避免每个 token 触发一次 SQL
- **边界**：
  - DB 文件损坏：`load` 抛 `CorruptSessionError`，不自动删
  - 启动时如检测到 `.tmp` 残留：提示用户恢复
- **错误处理**：SQL 写入失败时把事件放回队列前部并指数退避；连续 5 次失败则报错退出

### 3.6 模块 F6：TUI（`tui`）

- **框架**：Textual
- **布局**（单面板）：
  ```
  ┌─────────────────────────────────────────┐
  │ ● miniagent · claude-sonnet-4-6 · s_3a │  <- Header
  ├─────────────────────────────────────────┤
  │                                         │
  │ [user] 给 main.py 加 docstring          │
  │                                         │
  │ [assistant] 我来读一下文件...           │
  │   🔧 read_file(path="main.py")          │
  │   ✓ 23 lines                            │
  │   🔧 edit_file(path="main.py", ...)     │
  │   ✓ Wrote 89 bytes                      │
  │                                         │
  │ [assistant] 已添加 docstring:           │
  │ ```python                               │
  │ """Main entry point."""                 │
  │ ```                                     │
  │                                         │
  │                          [scrollable]   │
  ├─────────────────────────────────────────┤
  │ > _                                     │  <- Input
  ├─────────────────────────────────────────┤
  │ iter 3 · tokens 1240 · ctrl-c to stop   │  <- StatusBar
  └─────────────────────────────────────────┘
  ```
- **交互**：
  - Enter 提交消息 → 触发 agent.run() 后台 task
  - Ctrl+C 中断当前 agent 循环
  - `/reset` 软重置（清空 messages 但保留 session_id）
  - `/exit` 优雅退出
- **边界**：流式 token 到来时增量追加到对应消息 widget，不重绘整面板

---

## 4. 非功能性需求

### 4.1 性能

- 流式首 token 延迟 < 2s（受 LLM 自身延迟限制；本地解析 < 50ms）
- TUI 刷新 ≥ 30 fps；token 追加不卡顿
- 启动时间（容器内）< 3s
- 单 session 容量：支持 ≥ 1000 条消息不卡顿（SQLite 索引保证）

### 4.2 安全

- 容器以非 root 用户运行（uid=1000）
- 路径越界在工具层强制拒绝
- 容器外的文件系统**不可见**（除显式挂载）
- API key 仅从配置文件/env 读，不入 session.db
- 不向 LLM 发送任何非用户/agent 产生的内容

### 4.3 可用性

- 终端最小宽度 80 字符
- 支持 256 色与真彩色（自动降级）
- 所有错误信息在 TUI 中以人类可读形式呈现
- 配置文件缺失时打印一键修复指引

### 4.4 可观测性

- agent 循环每次产生的事件都进 session.db
- 启动时打印 session_id 便于 `--resume`
- 关键事件（重试、中断）记到 stderr 日志

---

## 5. 系统架构

### 5.1 组件图

```
┌──────────────┐    user input    ┌──────────────────┐
│   TUI        │ ────────────────▶│     Agent        │
│  (Textual)   │                  │   (async loop)   │
│              │ ◀──── events ─── │                  │
│ - chat log   │   (token, tool,  │  - call LLM      │
│ - input box  │    tool_result)  │  - exec tools    │
│ - status bar │                  │  - save session  │
└──────────────┘                  └────────┬─────────┘
                                           │
                            ┌──────────────┼──────────────┐
                            ▼              ▼              ▼
                       ┌────────┐    ┌────────┐    ┌──────────┐
                       │  LLM   │    │ Tools  │    │ Session  │
                       │ client │    │ (4个)  │    │(SQLite)  │
                       └────────┘    └────────┘    └──────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  Anthropic API   │
                   │  (BYOK, base_url │
                   │  可指向代理)      │
                   └──────────────────┘
```

### 5.2 数据流

1. 用户键入 → TUI Input widget → 调用 `agent.run(messages, on_event, session)`
2. agent.run 调 `llm.stream_step(messages, tools)` → 拿到 `(text, tool_calls)`
3. 通过 `on_event(AssistantDelta(text))` 把文本流式推给 TUI 渲染
4. 若有 tool_calls：循环执行 `tools.execute(...)`，每个结果通过 `on_event(ToolCallResult)` 推送
5. 同时 session 异步落盘
6. LLM 返回 `end_turn` → agent.run 返回，UI 解锁输入

### 5.3 外部依赖

- **运行时**：`anthropic` Python SDK、`textual`、`pydantic`
- **开发时**：`pytest`、`pytest-asyncio`、`respx`、`ruff`、`mypy`、`freezegun`
- **系统**：`uv`（包管理）、Docker（部署）、SQLite（Python 内建）
- **外部服务**：Anthropic Messages API（或兼容协议服务，通过 base_url 切换）

---

## 6. 数据模型

### 6.1 核心类型

```python
# Events（on_event 的参数）
@dataclass
class AssistantDelta:    text: str
@dataclass
class ToolCallStart:     call_id: str; name: str; args: dict
@dataclass
class ToolCallResult:    call_id: str; ok: bool; output: str; error: str | None
@dataclass
class EndTurn:           final_text: str
@dataclass
class AgentError:        message: str; recoverable: bool

# Tool 抽象
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Awaitable[ToolResult]]

# Tool 结果
@dataclass
class ToolResult:
    output: str
    error: str | None = None
    @property
    def is_error(self) -> bool: return self.error is not None

# Config（Pydantic）
class Config(BaseModel):
    llm: LLMConfig        # api_key, base_url, model
    paths: PathsConfig    # sessions_dir, config_dir
    agent: AgentConfig    # (预留字段，未来可加)
```

### 6.2 关系

- `Session` (1) → (N) `Message`
- `Tool` 静态注册到 `REGISTRY`（启动时导入）
- `Agent` 不持状态，所有状态通过 messages 序列传递

---

## 7. API 设计

TUI 是终端应用，不暴露 HTTP API；下面是**模块间接口**（最重要）。

### 7.1 `config.py`

```python
def load_config(cli_overrides: dict | None = None) -> Config: ...
```

### 7.2 `llm.py`

```python
class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str): ...
    async def stream_step(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[ToolCall]]: ...
```

### 7.3 `tools.py`

```python
REGISTRY: dict[str, Tool]

async def execute(name: str, args: dict) -> ToolResult: ...
def all_schemas() -> list[dict]: ...   # 喂给 LLM
```

### 7.4 `agent.py`

```python
Event = AssistantDelta | ToolCallStart | ToolCallResult | EndTurn | AgentError

async def run(
    messages: list[dict],
    on_event: Callable[[Event], None],
    session: SessionStore | None = None,
) -> list[dict]: ...   # 返回更新后的 messages
```

### 7.5 `session.py`

```python
class SessionStore:
    def __init__(self, db_path: Path): ...
    def create(self) -> str: ...  # 返回 session_id
    def get(self, session_id: str) -> SessionMeta: ...
    def list_recent(self, limit: int = 20) -> list[SessionMeta]: ...
    async def append_message(self, session_id: str, msg: dict) -> None: ...
    def load_messages(self, session_id: str) -> list[dict]: ...
    async def close(self) -> None: ...
```

### 7.6 `tui.py`（CLI 接口）

```bash
miniagent                          # 新建 session 并进入 TUI
miniagent --resume <session_id>    # 续接历史 session
miniagent --list                   # 列最近 20 个 session
miniagent --model <model>          # CLI 覆盖 config
miniagent --config <path>          # 指定 config 文件路径
```

---

## 8. 技术选型与理由

| 维度 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.12 | 生态成熟、SDK 全、Textual 流畅；课程接受 |
| TUI | Textual | 现代、异步、CSS-like 样式、Pilot 测试支持 |
| LLM SDK | 直调 `anthropic` Python SDK | 零抽象、零依赖；4 工具的循环 ~30 行，不需要框架 |
| 配置 | TOML + Pydantic | 比 .env 支持嵌套；Pydantic 提供 fail-fast 校验 |
| 持久化 | SQLite（标准库自带） | 单文件、ACID、零外部依赖；后台 flush 避免阻塞 |
| 沙箱 | Docker 容器 | 容器即天然沙箱；同时满足课程必做的容器化要求 |
| 包管理 | `uv` | 快 10–100×；与 ruff 同源；lock 文件保证 CI 一致 |
| 测试 | pytest + pytest-asyncio + respx | 行业标准；respx 可拦截真实 SDK 走过的 httpx |
| Lint/Type | ruff + mypy | ruff 一个工具替代 flake8+isort+black；mypy 严格模式 |
| CI | GitHub Actions | 课程默认；与 GitHub 仓库闭环 |

**未选 LangChain / Pydantic AI / LangGraph 的理由**：与"mini 基础"定位冲突；自身 ~30 行 agent 循环已够用；引框架增加 200+ 行抽象代码与一坨 transitive 依赖。

---

## 9. 验收标准

每模块"完成"的可观察判据：

| 模块 | 完成判据 |
|---|---|
| `config` | 缺字段启动报错信息清晰；合法配置能加载；`~` 展开正常；CLI 覆盖生效 |
| `llm` | respx 单测覆盖 200 OK / 401 不重试 / 429 退避重试 / 流式分块 / context overflow |
| `tools` | 4 工具各 ≥5 个单测全绿；路径越界测试必须存在且通过；bash 越界 token 拒绝测试存在 |
| `agent` | 跑通"用户问 → LLM 答 + 工具调用"全循环；Ctrl+C 中断能恢复 session |
| `session` | CRUD 单测全绿；损坏 DB 抛 `CorruptSessionError`；`--resume` 正确还原 messages |
| `tui` | Pilot 集成测试：发消息、看到响应、按 Ctrl+C 优雅退出、状态栏更新 |
| `Docker` | `docker build` 成功；`docker run -it` 真 tty 下能正常输入；README 命令一键跑通 |
| `E2E` | 容器内跑完"读 README → 改 README → TUI 看到结果"完整流程 |
| `CI` | `ci.yml` 全绿（含 ruff/mypy/pytest/docker build）；`e2e.yml` 手动 dispatch 绿 |

**整体"完成"**：上述所有项绿 + `make dev` 在干净环境跑通 + README 中"快速开始"段落的所有命令可一键执行。

---

## 10. 风险与未决问题

| 风险 | 应对 |
|---|---|
| Anthropic 工具调用 schema 与我们的 4 工具实现不一致 | 先用一个固定 prompt + 4 工具跑通；必要时调 system prompt 引导 |
| Textual 在容器 + 真 tty 环境下的键盘输入 | E2E 必须真在 `docker run -it` 里跑一遍，不只在 CI 假 tty |
| 流式 SSE 解析与 `anthropic` SDK 版本耦合 | 用 `uv.lock` 锁住 transitive 依赖 hash；CI 跑 `uv lock --check` |
| Docker 镜像大小预估 ~200MB | 接受；如需瘦身可换 `python:3.12-alpine`，但 musl 与部分 wheel 不兼容 |
| 用户的 `base_url` 指向非 Anthropic 服务商（智谱 GLM、月之暗面等）协议不完全一致 | `llm.py` 留 adapter 钩子（不是必须实现，留逃生口） |
| SQLite 写锁与 Textual 事件循环的协作 | 后台 flush task + `asyncio.Queue`；写失败指数退避 |
| 用户的 API key 因 BYOK 走错环境 | 启动时打印 `base_url` + `model` 前 4 字符 + `key ending in ...xxx`，便于肉眼确认 |

---

## 11. 范围之外（明确不做）

- 多 provider 自动切换
- 工具权限分级 / 黑白名单
- 子 agent / 任务委派
- Web UI / IDE 插件
- 自动 commit / PR 创建
- 上下文压缩 / 摘要
- 工具调用的人工审批（容器即沙箱，无需）
- 多用户 / 认证 / 远程访问
- 代码执行虚拟化（容器已隔离）
- 任何"高级"特性：MCP、subagent、RAG、记忆系统、语音输入...

---

## 12. 目录结构（最终形态）

```
AI4SE/
├── SPEC.md                          # 本文件
├── PLAN.md                          # writing-plans 产出（待）
├── SPEC_PROCESS.md                  # 冷启动验证记录（待）
├── AGENT_LOG.md                     # 持续维护
├── REFLECTION.md                    # 期末反思
├── README.md
├── pyproject.toml                   # uv 项目元数据 + 依赖
├── uv.lock                          # 锁定的依赖图
├── Makefile                         # dev/test/e2e/docker-build
├── Dockerfile                       # python:3.12-slim + uv
├── docker-compose.yml               # TUI 服务 + mock LLM (e2e 用)
├── .github/workflows/
│   ├── ci.yml                       # lint + unit + integration + docker build
│   └── e2e.yml                      # E2E（手动 dispatch）
├── docs/
│   ├── AI4SE_Final_Project0518.md
│   └── superpowers/specs/
│       └── 2026-06-01-mini-coding-agent-tui-design.md
├── src/miniagent/
│   ├── __init__.py
│   ├── __main__.py                  # python -m miniagent
│   ├── config.py                    # ~150 行
│   ├── llm.py                       # ~250 行
│   ├── tools.py                     # ~400 行
│   ├── agent.py                     # ~200 行
│   ├── tui.py                       # ~350 行
│   └── session.py                   # ~250 行
└── tests/
    ├── conftest.py                  # fixtures
    ├── unit/
    │   ├── test_config.py
    │   ├── test_tools.py
    │   ├── test_agent.py
    │   ├── test_llm.py
    │   └── test_session.py
    ├── integration/
    │   └── test_tui.py
    └── e2e/
        └── test_docker_smoke.py
```

总代码量估算：**src ~1600 行 + tests ~1800 行 + 项目元数据 ~200 行 = ~3600 行**（满足 3000–8000 区间下沿，仍有余量给后续打磨）。
