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
- ⏳ Phase 1: **awaiting user review of SPEC** — do NOT start coding
- ⏳ Phase 2: PLAN.md (via `superpowers:writing-plans`)
- ⏳ Phase 3: cold-start verification with a different agent
- ⏳ Phase 4: implementation (TDD, worktrees, subagents)
- ⏳ Phase 5: two-stage review + `finishing-a-development-branch`
- ⏳ Phase 6: Docker, CI
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
- `messages: list[dict]` is always in **Anthropic Messages API native format** (blocks, not raw text)
- `on_event: Callable[[Event], None]` is **sync**; events are dataclasses (`AssistantDelta` / `ToolCallStart` / `ToolCallResult` / `EndTurn` / `AgentError`)
- `session.append_message(...)` is **sync** (posts to internal `asyncio.Queue`; background task flushes to SQLite)
- `tools.execute(name, args) -> ToolResult` is **async**, returns `ToolResult(output, error)` — never raises for tool errors
- All file tools **reject paths that resolve outside the container's `/workspace`**

---

## 🛠️ Build / Test / Lint (will be defined in Phase 4)

The project skeleton intentionally has no `Makefile` or `pyproject.toml` yet — these land in Phase 4, driven by `PLAN.md`. Once they exist, the canonical targets will be:

```bash
# (planned, NOT yet available — these will be created in Phase 4)
make dev         # uv sync && uv run miniagent
make test        # uv run pytest                  (unit + integration)
make test-unit   # uv run pytest tests/unit       (TDD red/green loop)
make e2e         # uv run pytest tests/e2e -m e2e (manual, slow)
make lint        # uv run ruff check . && uv run mypy src
make docker      # docker build -t mini-agent .
make run         # docker run -it --rm -v $PWD:/workspace -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mini-agent
```

`uv.lock` must stay in sync — CI runs `uv lock --check`. Pin `anthropic` SDK to a minor version.

---

## 📂 First files to read in order

When you (a future Claude Code instance) start a session on this project, read in this order:

1. **[CLAUDE.md](CLAUDE.md)** — this file (hard rules, architecture map)
2. **[README.md](README.md)** — project status, directory layout, workflow
3. **[docs/AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md)** — course requirements + grading rubric
4. **[docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md](docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md)** — full design
5. **[AGENT_LOG.md](AGENT_LOG.md)** — prior agent activity, patterns to follow

If `PLAN.md` exists, also read it — it is the immediate task list.
