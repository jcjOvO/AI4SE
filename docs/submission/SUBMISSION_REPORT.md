# AI4SE 期末项目提交报告

> **项目**：Mini Coding Agent TUI
> **学生**：jcjovo
> **日期**：2026-06-14
> **GitHub 仓库**：[AI4SE](https://github.com/jcjovo/AI4SE)

---

## 一、交付物清单

| # | 交付物 | 状态 | 文件路径 |
|---|--------|------|----------|
| 1 | `SPEC.md`（设计文档） | ✅ 完成 | [docs/superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md](../superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md) |
| 2 | `PLAN.md`（实现计划） | ✅ 完成 | [docs/superpowers/plans/2026-06-01-mini-coding-agent-tui.md](../superpowers/plans/2026-06-01-mini-coding-agent-tui.md) |
| 3 | `SPEC_PROCESS.md`（过程文档） | ✅ 完成 | [docs/submission/SPEC_PROCESS.md](SPEC_PROCESS.md) |
| 4 | `SPEC_AND_PLAN_SUMMARY.md`（规约与计划汇总） | ✅ 完成 | [docs/submission/SPEC_AND_PLAN_SUMMARY.md](SPEC_AND_PLAN_SUMMARY.md) |
| 5 | 完整源代码 | ✅ 完成 | [src/miniagent/](../../src/miniagent/)（6 模块，~1,500 LOC） |
| 6 | `Dockerfile` + `docker-compose.yml` | ✅ 完成 | [Dockerfile](../../Dockerfile)、[docker-compose.yml](../../docker-compose.yml) |
| 7 | `README.md` | ✅ 完成 | [README.md](../../README.md) |
| 8 | `AGENT_LOG.md` | ✅ 完成 | [AGENT_LOG.md](../../AGENT_LOG.md)（29 条记录） |
| 9 | CI 配置 | ✅ 完成 | [.github/workflows/ci.yml](../../.github/workflows/ci.yml)、[.github/workflows/e2e.yml](../../.github/workflows/e2e.yml) |
| 10 | `REFLECTION.md` | ⏳ 待完成 | 待学生本人撰写 |

---

## 二、项目指标

| 指标 | 值 |
|------|-----|
| 总代码行数（src + tests） | ~2,800 LOC |
| src/miniagent/ | ~1,500 LOC |
| tests/ | ~1,300 LOC |
| 测试数量 | 68 tests collected（67 unit + integration + 1 e2e） |
| 测试通过率 | 100%（67/67 passed，1 e2e 手动运行） |
| ruff 检查 | ✅ All checks passed |
| mypy strict | ✅ Success: no issues found in 8 source files |
| Git commits | 67 commits |
| 核心模块数 | 5 个 + 1 辅助（config / llm / tools / agent / tui + session） |

---

## 三、工作流程执行记录

### 3.1 Superpowers 7 步工作流执行状态

| 步骤 | 状态 | 说明 |
|------|------|------|
| 1. brainstorming | ✅ 完成 | 9 轮澄清 + 3 方案对比 + 5 段设计确认，产出 SPEC |
| 2. writing-plans | ✅ 完成 | 19 个 task，每个 task 2–5 分钟，严格 TDD |
| 3. cold-start verification | ✅ 完成 | 用 OpenCode 验证 Task 1 + Task 3，详见 SPEC_PROCESS.md §4 |
| 4. subagent-driven-development | ✅ 完成 | 19/19 tasks，54 tests |
| 5. test-driven-development | ✅ 完成 | 严格 red→green→refactor 循环 |
| 6. code-review | ✅ 完成 | 修复 6 项 Important issues |
| 7. finishing-a-development-branch | ✅ 完成 | feature branch fast-forward merge 到 main |

### 3.2 Phase 详细记录

| Phase | 时间 | 状态 | 关键产出 |
|-------|------|------|----------|
| Phase 0 | 2026-06-01 | ✅ | 仓库初始化，建立目录骨架 |
| Phase 1 | 2026-06-01 | ✅ | SPEC（commit `e1f3b7c` + `92adb2f`） |
| Phase 2 | 2026-06-01 | ✅ | PLAN（19 tasks） |
| Phase 3 | 2026-06-01 | ✅ | 冷启动验证（OpenCode 验证 Task 1 + Task 3） |
| Phase 4 | 2026-06-01 | ✅ | 19/19 tasks 完成，54 tests，code review fixes merged |
| Phase 5 | 2026-06-01 | ✅ | feature branch 合并到 main（fast-forward） |
| Phase 6 | 2026-06-13 | ✅ | Docker 实际构建 + 真 LLM 手动测试 + TUI 美化 + Bug 修复 |
| Phase 7 | - | ⏳ | REFLECTION.md（待完成） |

---

## 四、SPEC 关键设计决策

### 4.1 架构选择

- **5 核心模块 + 1 辅助**：config / llm / tools / agent / tui + session（persistence helper）
- **不用 Agent 框架**：直调 Anthropic SDK，~30 行 agent 循环已够用
- **容器即沙箱**：无需内部审批流程，Docker 容器天然隔离
- **SQLite + asyncio.Queue**：异步 flush 避免阻塞 agent 循环

### 4.2 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12 | 生态成熟、SDK 全、Textual 流畅 |
| TUI | Textual | 现代、异步、CSS-like 样式、Pilot 测试支持 |
| LLM SDK | 直调 anthropic SDK | 零抽象、零依赖 |
| 配置 | TOML + Pydantic | 比 .env 支持嵌套；Pydantic 提供 fail-fast 校验 |
| 持久化 | SQLite | 单文件、ACID、零外部依赖 |
| 包管理 | uv | 快 10–100×；lock 文件保证 CI 一致 |
| Lint/Type | ruff + mypy strict | 行业标准 |

### 4.3 范围之外（明确不做）

- 多 provider 自动切换
- 工具权限分级 / 黑白名单
- 子 agent / 任务委派
- Web UI / IDE 插件
- 自动 commit / PR 创建
- 上下文压缩 / 摘要
- 工具调用的人工审批
- 多用户 / 认证 / 远程访问
- MCP、RAG、记忆系统、语音输入

---

## 五、PLAN 执行记录

### 5.1 Task 完成状态

| Task | 描述 | 状态 | Commit |
|------|------|------|--------|
| 1 | Project skeleton + uv + test infrastructure | ✅ | `79bd723` |
| 2 | Config module — Pydantic + TOML | ✅ | `9ede918` |
| 3 | Tools module skeleton | ✅ | `10e2d94` |
| 4 | read_file tool | ✅ | `10e2d94` |
| 5 | write_file tool | ✅ | `b851415` |
| 6 | edit_file tool | ✅ | `b851415` |
| 7 | bash tool + sandbox | ✅ | `b851415` |
| 8 | SessionStore (sync CRUD) | ✅ | `b851415` |
| 8b | AsyncSessionStore (non-blocking) | ✅ | `b851415` |
| 9 | LLMClient skeleton (SSE streaming) | ✅ | `b851415` |
| 10 | LLMClient retry (429/5xx/529) | ✅ | `b851415` |
| 11 | Agent loop (Event-driven run()) | ✅ | `b851415` |
| 12 | TUI App skeleton (Textual 4 widget) | ✅ | `b851415` |
| 13 | TUI wire input → agent.run | ✅ | `b851415` |
| 14 | CLI (__main__.py argparse + wiring) | ✅ | `c44ea9b` |
| 15 | Dockerfile + docker-compose | ✅ | `11bd2c4` |
| 16 | CI (ci.yml + e2e.yml) | ✅ | `dfcfdda` |
| 17 | README (quick-start + commands) | ✅ | `347ec50` |
| 18 | E2E mock LLM + agent.run smoke | ✅ | `03b22c6` |
| 19 | Wrap-up + AGENT_LOG | ✅ | `03ddfa3` |

### 5.2 Code Review Fixes

| Issue | 严重性 | 修复 |
|-------|--------|------|
| AsyncSessionStore 是死代码 | Important | Wire 到 __main__.py + TUI |
| _BACKOFF_BASE = 0.01 生产太激进 | Important | 改为 env var 配置，默认 1.0s |
| --resume 不真的 resume | Important | TUI 渲染历史消息 |
| bash sandbox 可被 shell expansion 绕过 | Important | 文档说明 + 测试钉住行为 |
| _ToolsAdapter 重复 | Important | 改为 tools.py 单例 |
| TUI._current_assistant_text 死代码 | Important | 删除 + 简化渲染逻辑 |

---

## 六、测试覆盖

### 6.1 测试分布

| 测试类型 | 数量 | 覆盖模块 |
|----------|------|---------|
| unit | 52 | config / llm / tools / session / agent / __main__ |
| integration | 2 | TUI (Textual pilot) |
| e2e | 1 | mock LLM + agent.run smoke |
| **总计** | **55**（+ 13 新增在 Phase 6） | |

### 6.2 关键测试场景

- **Config**：minimal load / missing api_key / CLI override
- **Tools**：4 工具各 5–6 个测试，覆盖 happy path + error path + sandbox traversal
- **Session**：CRUD roundtrip / corrupt DB / async non-blocking
- **LLM**：SSE streaming / 429 retry / 401 no-retry / retry exhausted
- **Agent**：text-only / tool call + result / tool error reflow / cancellation
- **TUI**：启动渲染 / input → agent.run / history replay

---

## 七、Docker 部署

### 7.1 构建与运行

```bash
# 构建镜像
make docker-build
# 或
docker build -t mini-agent .

# 运行容器
make docker-run
# 或
docker run -it --rm \
  -v $PWD:/workspace \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  mini-agent
```

### 7.2 Dockerfile 特点

- **多阶段构建**：python:3.12-slim + uv 安装
- **非 root 用户**：uid=1000，安全性
- **最小镜像**：只安装生产依赖（不含 dev 依赖）

---

## 八、CI/CD 配置

### 8.1 ci.yml（push/PR 触发）

```
ruff check → ruff format --check → mypy src → pytest -m "not e2e" → docker build
```

### 8.2 e2e.yml（手动 dispatch + 每日定时）

```
手动触发：workflow_dispatch
每日定时：schedule (cron)
```

---

## 九、AGENT_LOG 摘要

AGENT_LOG.md 包含 **28 条记录**，覆盖从 Phase 0 到 Phase 6 的完整决策路径：

| # | 时间 | 阶段 | 摘要 |
|---|------|------|------|
| 0 | 2026-06-01 | Phase 0 | 仓库初始化 |
| 1 | 2026-06-01 | Phase 1 | brainstorming → SPEC（9 轮澄清） |
| 2 | 2026-06-01 | Phase 1 | init skill → CLAUDE.md |
| 3–19 | 2026-06-01 | Phase 4 | 19/19 tasks TDD 实现 |
| 20 | 2026-06-01 | Phase 4 | 收尾总结 |
| 21 | 2026-06-01 | Phase 4 | code review fixes（6 项 Important） |
| 22 | 2026-06-01 | Phase 4 | branch finish → merge to main |
| 23 | 2026-06-13 | Phase 6 | 沙箱路径修复 |
| 24 | 2026-06-13 | Phase 6 | 多轮对话修复 |
| 25 | 2026-06-13 | Phase 6 | TUI 美化（暗色主题 + 面板 + spinner） |
| 26 | 2026-06-13 | Phase 6 | 修复 tool_use 缺少 tool_result |
| 27 | 2026-06-13 | Phase 6 | 修复空 content 消息 |
| 28 | 2026-06-13 | Phase 6 | 添加结构化 System Prompt |

**关键教训**：
- TDD 纪律带来的复利：spec bug 在 RED 阶段就能抓到
- 「spec 滞后于环境」是最高频 bug 源：每 3-4 task 就遇到一次
- e2e test 是「发现 wire-up bug」的唯一途径
- AGENT_LOG 是「why & how」的决策日志，比 git log 强 10 倍

---

## 十、后续待完成

1. **REFLECTION.md**（1500–2500 字反思报告）— 待学生本人撰写
2. **Docker Hub 推送**（可选）— 提供公开镜像地址
3. **演示视频**（可选）— 5–10 分钟演示视频链接

---

## 附录：关键文件索引

| 文件 | 说明 |
|------|------|
| [SPEC.md](../superpowers/specs/2026-06-01-mini-coding-agent-tui-design.md) | 设计规约（Phase 1 产出） |
| [PLAN.md](../superpowers/plans/2026-06-01-mini-coding-agent-tui.md) | 实现计划（Phase 2 产出） |
| [SPEC_PROCESS.md](SPEC_PROCESS.md) | 规约与计划生成过程文档 |
| [AGENT_LOG.md](../../AGENT_LOG.md) | 智能体协作过程记录（28 条） |
| [README.md](../../README.md) | 项目简介、安装、运行、Docker 命令 |
| [Dockerfile](../../Dockerfile) | 多阶段构建（python:3.12-slim + uv） |
| [docker-compose.yml](../../docker-compose.yml) | 一键启动配置 |
| [ci.yml](../../.github/workflows/ci.yml) | CI 配置（lint + type + test + docker build） |
| [e2e.yml](../../.github/workflows/e2e.yml) | E2E 配置（手动 + 每日定时） |
