# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project: Mini Coding Agent TUI

A terminal-based, multi-tool, multi-turn coding agent in a single Docker image. **BYOK**, **Python 3.12 + Textual + uv**, **SQLite** session storage. Sandbox = the container itself (no internal approval flow). 5 functional modules + 1 persistence helper. ~3,600 LOC target.

For full design rationale, constraints, and the 5+1 module breakdown → **[docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md](docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md)** (the SPEC).

For project context and grading rubric → **[README.md](README.md)** + **[docs/AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md)**.

---

## 🚨 Hard Rule #1 — The Diary (AGENT_LOG.md)

**Every meaningful action MUST be logged to [AGENT_LOG.md](AGENT_LOG.md)** before the corresponding commit lands. The log is graded as **process evidence** by the course.

Each entry MUST follow the schema in [docs/AI4SE_Final_Project0518.md §4.9](docs/AI4SE_Final_Project0518.md):

- **时间戳与 task 编号** (timestamp + task number)
- **触发的 Superpowers 技能** (which skill fired)
- **关键 prompt / context** (what you were told)
- **subagent 输出** (key fragments, commit hashes, or links)
- **人工干预** (what the human changed and why)
- **学到的教训** (reusable prompt templates, pitfalls, strategies)

When in doubt, log more, not less. Skipping a log row is a process violation.

---

## 🚨 Hard Rule #2 — Follow the 7-step Superpowers workflow

This is an **AI4SE course project**. The 7-step workflow is non-negotiable:

```
brainstorming → writing-plans → subagent-driven-development
             → TDD (red/green/refactor) → code-review → finishing-a-development-branch
```

**Status (as of 2026-06-01):**
- ✅ Phase 0: repo init
- ✅ Phase 1: SPEC written (commits `e1f3b7c`, `92adb2f`)
- ✅ Phase 2: PLAN written (`docs/superpowers/plans/2026-06-01-mini-coding-agent-tui.md`)
- ⏳ Phase 3: cold-start verification — **skipped by user authorization**
- ✅ Phase 4: implementation complete (19/19 tasks, 54 tests, merged to main)
- ✅ Phase 4 review: code-review fixes merged (6 Important issues resolved)
- ✅ Phase 4 branch finish: `feature/phase-4-impl-tasks-1-3` merged to `main` via `--ff-only`
- ⏳ Phase 6: Docker real build + manual LLM test
- ⏳ Phase 7: REFLECTION.md

**Never write implementation code before SPEC + PLAN are both committed and the cold-start verification (Phase 3) has been run.** TDD is a hard requirement — no "implement then test" allowed.

---

## 🚨 Hard Rule #3 — Stay inside the spec's "scope of not-doing"

The SPEC explicitly lists things we are **not** building (§11 of the spec). Do not "helpfully" add:

- Multi-provider auto-switching
- Tool permission tiers / allow-deny lists
- Sub-agents / task delegation
- Web UI / IDE plugin
- Auto-commit / PR creation
- Context compression / summarization
- Manual tool-call approval flow
- Multi-user / auth / remote access
- MCP, RAG, memory systems, voice input, or any "advanced" feature

If a feature isn't in SPEC §3 (functional spec) or §4 (non-functional), it does not belong in v1.

---

## 🏗️ Architecture (the big picture)

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

**5 functional modules** (the course's "core modules" count) + 1 persistence helper:

| Module | File | Responsibility |
|---|---|---|
| `config` | `src/miniagent/config.py` | Load + validate `config.toml`; parse CLI; Pydantic models |
| `llm` | `src/miniagent/llm.py` | Thin async wrapper around `anthropic` SDK; stream → `(text, tool_calls)`; retries |
| `tools` | `src/miniagent/tools.py` | Registry + 4 tool handlers: `read_file` / `write_file` / `edit_file` / `bash` |
| `agent` | `src/miniagent/agent.py` | Pure async loop; takes `messages + on_event + session`; emits events |
| `tui` | `src/miniagent/tui.py` | Textual app: header, scrollable log, input box, status bar |
| `session` | `src/miniagent/session.py` | SQLite store; async-flush queue; **persistence helper, not a 6th core module** |

**Critical contracts** (don't break these — they are the seams between modules):
- `messages: list[dict[str, Any]]` is always in **Anthropic Messages API native format** (blocks, not raw text)
- `on_event: Callable[[Event], None]` is **sync**; events are dataclasses (`AssistantDelta` / `ToolCallStart` / `ToolCallResult` / `EndTurn` / `AgentError`)
- `session.append_message(...)` is **sync** (posts to internal `asyncio.Queue`; background task flushes to SQLite)
- `tools.execute(name, args) -> ToolResult` is **async**, returns `ToolResult(output, error)` — never raises for tool errors
- All file tools **reject paths that resolve outside the container's `/workspace`**
- `tools` singleton (`from miniagent.tools import tools`) exposes `all_schemas()` / `execute()` — use this, not `REGISTRY` directly
- `AsyncSessionStore` wraps `SessionStore` with non-blocking queue — wire it in `__main__.py`, not sync store

---

## 🛠️ Build / Test / Lint

All commands use `uv`. The Makefile wraps them for convenience.

```bash
# Setup
make dev                  # uv sync --extra dev

# Test (TDD red/green loop)
make test-unit            # uv run pytest tests/unit -v
make test-integration     # uv run pytest tests/integration -v
make test                 # uv run pytest -m "not e2e" -v   (unit + integration)
make e2e                  # uv run pytest tests/e2e -v       (manual, slow)

# Lint / Type
make lint                 # uv run ruff check src tests && uv run ruff format --check src tests
make type                 # uv run mypy src

# Docker
make docker-build         # docker build -t mini-agent .
make docker-run           # docker run -it --rm -v $PWD:/workspace -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mini-agent

# Run locally
uv run miniagent          # launch TUI (needs ANTHROPIC_API_KEY in env or config.toml)
uv run miniagent --help   # show CLI options

# Lock
make lock-check           # uv lock --check (CI enforces this)
```

**Running a single test:**
```bash
uv run pytest tests/unit/test_tools.py -v                     # one file
uv run pytest tests/unit/test_tools.py -v -k "read_file"     # by name
uv run pytest tests/unit/test_tools.py::test_basic_read -v   # exact test
```

**CI pipeline** (`.github/workflows/ci.yml`): `ruff check` → `ruff format --check` → `mypy src` → `pytest -m "not e2e"` → `docker build`. Runs on push to `main` and PRs.

`uv.lock` must stay in sync — CI runs `uv lock --check`. Pin `anthropic` SDK to a minor version.

---

## ⚠️ Conventions learned from Phase 4 (hard-won, don't ignore)

These emerged from 19 TDD tasks — violating them will cause mypy/ruff failures or test bugs:

1. **All `dict` annotations must be `dict[str, Any]`**, never bare `dict`. Same for `list` → `list[Any]`. mypy strict enforces this. `from typing import Any` is always in scope.

2. **All `ORDER BY <timestamp>` must include a tie-breaker**: `ORDER BY updated_at DESC, rowid DESC`. SQLite `rowid` is the monotonic insertion sequence — UUID `id` is NOT.

3. **Tests that touch env-var-reading code must `monkeypatch.setenv`**. Handlers read `MINI_AGENT_WORKSPACE` / `MINI_AGENT_LLM_BACKOFF_BASE` from `os.environ`. Tests that don't set these will silently use the host's values.

4. **`# noqa: F401` is for "expressing the public API surface"** in test imports. When a test file imports symbols it doesn't use directly, this is intentional — it verifies the symbol is importable.

5. **Textual `App` must be `App[None]`** (textual 0.80+ requires parameterized generic).

6. **`asyncio.TimeoutError` → `TimeoutError`** (Python 3.11+ deprecation, ruff UP041).

7. **`Path.resolve()` in async code → `await asyncio.to_thread(path.resolve)`** (ruff ASYNC240: may do filesystem I/O).

8. **Test assertions for subprocess paths should use `path.name`** (leaf), not `str(path)`. Windows MSYS/Git Bash translates paths.

9. **`_BACKOFF_BASE` / `_MAX_RETRIES` / timeout constants must be env-configurable** (`os.environ.get(...)` with sensible default). Production and test needs differ.

10. **`CancelledError` must be re-raised, never swallowed** — it's control flow for TUI task cancellation.

---

## 📂 First files to read in order

When you (a future Claude Code instance) start a session on this project, read in this order:

1. **[CLAUDE.md](CLAUDE.md)** — this file (hard rules, architecture map)
2. **[README.md](README.md)** — project status, directory layout, workflow
3. **[docs/AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md)** — course requirements + grading rubric
4. **[docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md](docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md)** — full design
5. **[AGENT_LOG.md](AGENT_LOG.md)** — prior agent activity, patterns to follow

The implementation plan is at **[docs/superpowers/plans/2026-06-01-mini-coding-agent-tui.md](docs/superpowers/plans/2026-06-01-mini-coding-agent-tui.md)** (19 tasks, all completed).
