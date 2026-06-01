# Mini Coding Agent TUI

> *Spec-Driven, Subagent-Built, Human-Owned.*

A terminal-based, multi-tool, multi-turn coding agent in a single Docker image. Built with **Python 3.12 + Textual + uv**, backed by **SQLite** session storage. BYOK (Bring Your Own Key) — point it at any Anthropic-compatible API.

本仓库是 **AI4SE 期末项目** 的工程化交付物：使用 **[Superpowers](https://github.com/obra/superpowers)** 框架，按 7 步工作流（brainstorming → writing-plans → subagent-driven-development → TDD → code-review → finishing-a-development-branch）从规约出发、由 subagent 自主执行、人类全程评审，完成一个具有一定规模的真实软件项目。

课程要求与评分细则参见 [docs/AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md)。

---

## 项目状态

- [x] **Phase 0**：仓库初始化
- [x] **Phase 1**：`brainstorming` → 产出 [SPEC](docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md)
- [x] **Phase 2**：`writing-plans` → 产出 [PLAN](docs/superpowers/plans/2026-06-01-mini-coding-agent-tui.md)
- [x] **Phase 3**：冷启动验证 — *跳过（用户授权）*
- [x] **Phase 4**：`subagent-driven-development` + TDD → 19/19 tasks 完成，54 tests，code review fixes merged
- [x] **Phase 5**：`finishing-a-development-branch` → feature branch 合并到 main（fast-forward）
- [ ] **Phase 6**：Docker 实际构建 + 真 LLM 手动测试
- [ ] **Phase 7**：[REFLECTION.md](REFLECTION.md) 反思报告

**当前指标**：54 tests passed · ruff 0 error · mypy strict 0 error · ~1,200 LOC（6 模块）

详细过程记录见 [AGENT_LOG.md](AGENT_LOG.md)（22 条记录，覆盖从 Phase 0 到 branch finish 的完整决策路径）。

---

## 架构

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

**5 核心模块 + 1 辅助**：

| 模块 | 文件 | 职责 |
|---|---|---|
| `config` | [src/miniagent/config.py](src/miniagent/config.py) | TOML + Pydantic 校验 + CLI overlay + fail-fast |
| `llm` | [src/miniagent/llm.py](src/miniagent/llm.py) | Anthropic Messages API SSE 流式 + 429/5xx 重试 + 指数退避 |
| `tools` | [src/miniagent/tools.py](src/miniagent/tools.py) | 4 个工具：`read_file` / `write_file` / `edit_file` / `bash` + sandbox 路径校验 |
| `agent` | [src/miniagent/agent.py](src/miniagent/agent.py) | 5 种事件 + async run() 循环 + tool reflow + CancelledError 透传 |
| `tui` | [src/miniagent/tui.py](src/miniagent/tui.py) | Textual App + 4 widget + input → agent.run + event 渲染 |
| `session` | [src/miniagent/session.py](src/miniagent/session.py) | SQLite CRUD + AsyncSessionStore（non-blocking queue + drain-on-close）|

---

## 目录结构

```
.
├── src/miniagent/
│   ├── __init__.py
│   ├── __main__.py          # CLI 入口（argparse + module wiring）
│   ├── config.py             # 配置加载 + 校验
│   ├── llm.py                # LLM 客户端（SSE 流式 + 重试）
│   ├── tools.py              # 工具注册 + 4 个 handler + sandbox
│   ├── agent.py              # Agent 循环 + 事件
│   ├── tui.py                # Textual TUI 应用
│   └── session.py            # SQLite 会话存储
├── tests/
│   ├── unit/                 # 单元测试（52 个）
│   ├── integration/          # 集成测试（2 个，TUI）
│   └── e2e/                  # 端到端测试（1 个，mock LLM）
├── scripts/
│   └── mock_anthropic.py     # E2E 用 mock HTTP server
├── docs/
│   ├── AI4SE_Final_Project0518.md        # 课程要求 + 评分细则
│   └── superpowers/
│       ├── specs/            # 设计规约（Phase 1）
│       └── plans/            # 实现计划（Phase 2）
├── .github/workflows/
│   ├── ci.yml                # lint → type → test → docker build
│   └── e2e.yml               # 手动 + 每日定时 E2E
├── Dockerfile                # 多阶段构建（python:3.12-slim + uv）
├── docker-compose.yml        # 一键启动
├── Makefile                  # 开发命令快捷入口
├── pyproject.toml            # 项目元数据 + 依赖 + ruff/mypy 配置
├── CLAUDE.md                 # Claude Code 操作手册
├── AGENT_LOG.md              # 智能体协作过程记录（22 条）
└── README.md                 # 本文件
```

---

## 运行

### Quick start

```bash
# 1. 配置 API Key（二选一）
#    方式 A：环境变量
export ANTHROPIC_API_KEY="sk-ant-..."

#    方式 B：配置文件
mkdir -p ~/.config/mini-agent
cat > ~/.config/mini-agent/config.toml <<'EOF'
[llm]
api_key = "sk-ant-..."
base_url = "https://api.anthropic.com"
model = "claude-sonnet-4-6"
EOF

# 2. 安装依赖
make dev                  # uv sync --extra dev

# 3. 启动 TUI
uv run miniagent
```

### Docker

```bash
make docker-build
docker run -it --rm -v $PWD:/workspace -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mini-agent
```

### 常用命令

| 命令 | 说明 |
|---|---|
| `make dev` | 安装依赖 |
| `make test-unit` | 跑单元测试 |
| `make test` | 跑单元 + 集成测试 |
| `make e2e` | 跑端到端测试（手动，较慢） |
| `make lint` | ruff check + format check |
| `make type` | mypy 类型检查 |
| `make docker-build` | 构建 Docker 镜像 |
| `make docker-run` | 在容器中启动 TUI |
| `uv run miniagent --resume <id>` | 恢复之前的会话 |
| `uv run miniagent --list` | 列出最近会话 |
| `uv run miniagent --model <name>` | 覆盖默认模型 |

---

## 开发

### 测试

```bash
make test                 # unit + integration（54 tests）
make test-unit            # 仅 unit（52 tests）
make test-integration     # 仅 integration（2 tests）
make e2e                  # e2e（1 test，需网络）

# 跑单个测试
uv run pytest tests/unit/test_tools.py -v -k "read_file"
```

### Lint / Type

```bash
make lint                 # ruff check + format check
make type                 # mypy strict
```

项目使用 **ruff**（E/F/I/B/UP/N/SIM/ASYNC 全套规则）和 **mypy strict** 模式。所有 `dict` 注解必须写 `dict[str, Any]`，不能用 bare `dict`。

### CI

`.github/workflows/ci.yml` 在 push 到 `main` 和 PR 时自动运行：`ruff check` → `ruff format --check` → `mypy src` → `pytest -m "not e2e"` → `docker build`。

---

## 致谢

- [Superpowers](https://github.com/obra/superpowers) — Jesse Vincent 的编码智能体技能框架
- [Anthropic](https://www.anthropic.com) — Claude API
- [Textual](https://textual.textualize.io) — TUI 框架
