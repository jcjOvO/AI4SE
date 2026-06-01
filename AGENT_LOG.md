# AGENT_LOG.md — 智能体协作过程记录

> 按时间顺序记录与编码智能体（含 Superpowers 框架内 subagent）协作的关键节点。
> 每条记录应包含：时间戳 / task 编号 / 触发的 Superpowers 技能 / 关键 prompt 与 context / subagent 输出摘要 / 人工干预 / 学到的教训。
>
> 详细字段说明见 [docs/AI4SE_Final_Project0518.md §4.9](docs/AI4SE_Final_Project0518.md)。

---

## 日志记录规则

- **每次写作都要写 log**（用户于 2026-06-01 在会话中明确指示）。
- 范围：任何 `Write` / `Edit` 工具调用 —— 创建新文件、修改现有文件、产出非平凡的文本输出 —— 都必须在 [本文件](AGENT_LOG.md) 追加一条记录。
- 例外（可省略记录）：纯 typo / 空白修正 / 提交信息微调。
- 极小改动可省去 "学到的教训" 字段，但 **时间 / task / 触发技能 / 关键 prompt 或 context / subagent 输出或人工干预** 五个字段必须保留。
- 每追加一条记录，必须同步更新本文件顶部的 **索引表**。
- **元规则本身也是日志条目**（如本条规则的建立）。

---

## 索引

| # | 时间 | 阶段 | 触发技能 | 摘要 |
|---|------|------|----------|------|
| 0 | 2026-06-01 | Phase 0 初始化 | — | 仓库初始化，建立目录骨架与文档占位符 |
| 1 | 2026-06-01 | 元规则 | — | 用户指示"以后每次写作都要写 log"，建立日志记录规则 |

---

## #0 — 2026-06-01 — Phase 0：仓库初始化

- **任务**：建立项目骨架，使后续 brainstorming → writing-plans → 实现的工作流有干净的起点。
- **触发的 Superpowers 技能**：无（项目初始化的 "Phase 0"，在 `brainstorming` 启动之前）
- **关键 prompt / context**：用户原始请求"请你根据文档，初始化一下该项目，并且进行 initial commit"；课程文档要求"在 SPEC 与 PLAN 完成并通过冷启动验证之前，禁止编写任何实现代码"。
- **subagent 输出摘要**：N/A（此阶段为人类 + 主 agent 直接搭建骨架）
- **人工干预**：将课程文档 [AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md) 放入 `docs/`；建立 `SPEC.md` / `PLAN.md` / `SPEC_PROCESS.md` / `AGENT_LOG.md` / `REFLECTION.md` / `README.md` 的占位路径（在 `README.md` 的目录结构中列出，但不创建空文件，避免污染初始 commit）。
- **学到的教训**：
  - 严格遵守"先 spec、后实现"的硬规则 —— initial commit 只放骨架，不放任何 src/ 或 tests/ 内容。
  - 后续每个 task 完成时按规范追加一条记录，并在 `PLAN.md` 勾掉对应项、附 commit hash。

---

## #1 — 2026-06-01 — 元规则：日志记录规则建立

- **任务**：将用户会话指令"以后每次写作都要写 log"沉淀为可复用的工程纪律。
- **触发的 Superpowers 技能**：无（规则本身的元操作，不属于项目实现阶段）
- **关键 prompt / context**：用户在打开 [AGENT_LOG.md](AGENT_LOG.md) 后明确指示"记住：以后每次写作都要写log"。
- **subagent 输出摘要**：N/A
- **人工干预**：
  - 写入 3 条项目级 memory：[ai4se-final-project-overview](.claude%2Fprojects%2Fd--AI4SE%2Fmemory%2Fai4se-final-project-overview.md)、[feedback-log-every-writing](.claude%2Fprojects%2Fd--AI4SE%2Fmemory%2Ffeedback-log-every-writing.md)、[superpowers-workflow-strictness](.claude%2Fprojects%2Fd--AI4SE%2Fmemory%2Fsuperpowers-workflow-strictness.md)，并在 [MEMORY.md](.claude%2Fprojects%2Fd--AI4SE%2Fmemory%2FMEMORY.md) 索引。
  - 在 [AGENT_LOG.md](AGENT_LOG.md) 顶部新增 **"日志记录规则"** 章节，固化本规则的覆盖范围、字段要求、索引同步要求。
  - 索引表追加条目 #1。
- **学到的教训**：
  - 用户的会话级指令应该沉淀到 `memory/`，避免下次会话忘记；工程纪律的"为何要做"写在 memory 的 frontmatter 与正文里，why + how to apply 一起保存。
  - 规则本身的建立也是一次 writing，按"每次写作都要写 log"的标准必须自指地记录 —— 这避免了"规则只口头存在、不被审计"的风险。
  - 后续若用户放宽或调整此规则，需追加 #N 条目记录变更，并相应更新 memory。
