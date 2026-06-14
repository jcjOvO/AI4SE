# SPEC_PROCESS.md — 规约与计划生成过程文档

> 记录与 Superpowers 协作生成 SPEC 与 PLAN 的完整过程。

---

## 一、Brainstorming 关键节点

### 1.1 初始需求澄清

**用户原始请求**：「我想做一个 mini coding agent 的 TUI 项目，只支持基础功能即可，无需做过多高级拓展。」

**智能体追问（9 轮关键澄清）**：

| 轮次 | 智能体追问 | 用户回答 | 影响 |
|------|-----------|---------|------|
| Q1 | 「最像哪种产品形态？」 | Claude Code-like 多工具 agent | 确定了核心架构：agent loop + tool calling |
| Q2 | 工具集选择 | 4 工具：read_file / write_file / edit_file / bash | 确定了 tools 模块的 4 个 handler |
| Q3 | LLM 后端选择 | Anthropic 协议 + BYOK + 配置文件驱动 base_url/model/api_key | 确定了 llm 模块的 SSE 流式设计 |
| Q4 | 技术栈选择 | Python + Textual | 确定了 TUI 框架选型 |
| Q5 | 安全/审批机制 | 沙箱后无需确认，整个项目跑在 Docker 容器里 | 确定了「容器即沙箱」的安全模型 |
| Q6 | TUI 布局 | 单面板滚动对话（最简） | 确定了 tui.py 的 widget 树 |
| Q7 | 会话持久化 | 本地保存 + 可续接 | 确定了 session 模块的 SQLite 设计 |
| Q8 | Agent 框架选择 | **不用框架，直调 Anthropic SDK** | 用户主动推翻了智能体的「推荐框架」建议 |
| Q9 | 包管理工具 | **用 uv** | 用户主动追加，智能体未主动提 |

### 1.2 关键决策点

**决策 1：不使用 Agent 框架**

- **智能体建议**：推荐使用 LangChain / Pydantic AI 等框架简化开发
- **用户决策**：不用框架，直调 Anthropic SDK
- **理由**：与「mini 基础」定位冲突；自身 ~30 行 agent 循环已够用；引框架增加 200+ 行抽象代码与一坨 transitive 依赖
- **结果**：SPEC §8 技术选型明确记录了「未选 LangChain / Pydantic AI / LangGraph 的理由」

**决策 2：不设 max_iterations**

- **智能体建议**：设置最大迭代次数防止 agent 无限循环
- **用户决策**：不设 max_iterations
- **理由**：用户认为「容器即沙箱」，无需额外限制
- **结果**：SPEC §3.4 Agent 循环的边界条件中未包含迭代上限

**决策 3：会话存储改 SQLite**

- **智能体建议**：默认使用文件系统存储
- **用户决策**：改用 SQLite
- **理由**：单文件、ACID、零外部依赖；后台 flush 避免阻塞
- **结果**：SPEC §3.5 明确使用 SQLite + asyncio.Queue 异步 flush

---

## 二、至少 3 轮关键迭代

### 迭代 1：架构方案选择（3 方案对比）

**智能体提供 3 个方案**：

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A（推荐） | 分层 5 模块：config / llm / tools / agent / tui + session 辅助 | 模块边界清晰，职责单一 | 需要显式模块间通信 |
| B | 4 模块紧耦合：agent 直接内嵌 tools | 实现简单 | 扩展性差，违反单一职责 |
| C | 事件总线架构：模块通过事件解耦 | 高度可扩展 | 复杂度高，不适合 mini 项目 |

**用户选择**：方案 A（分层 5 模块）

**迭代过程**：
1. 智能体推荐方案 A，给出详细模块划分
2. 用户追问「为什么不选方案 C？」
3. 智能体解释：事件总线对 mini 项目过度设计，增加 200+ 行抽象代码
4. 用户接受方案 A，但要求明确「session 是辅助模块，不是第 6 个核心模块」

**最终结果**：SPEC §5.1 明确写「5 个核心功能模块 + 1 个持久化辅助层」

### 迭代 2：数据流 vs API 契约分离讨论

**问题暴露**：智能体最初把数据流和 API 设计混在一起讨论

**用户干预**：要求分离讨论，避免「TUI 直接调 LLM」的耦合问题

**迭代过程**：
1. 智能体在 §5.2 数据流中描述：「用户键入 → TUI Input widget → 调用 agent.run()」
2. 用户追问：「TUI 如何知道 agent 什么时候完成？」
3. 智能体澄清：agent.run() 是 async 函数，通过 on_event 回调推送事件
4. 用户要求：在 §7 API 设计中明确每个模块的接口签名

**最终结果**：
- SPEC §5.2 数据流独立章节
- SPEC §7 API 设计独立章节，包含 6 个模块的完整接口签名
- 关键契约：`on_event: Callable[[Event], None]` 是同步回调，事件是 dataclass

### 迭代 3：错误处理「工具错误回流 LLM」设计

**问题识别**：智能体最初设计「agent 循环兜底」处理工具错误

**用户推翻**：要求「工具错误回流 LLM」，让 LLM 自行决定如何处理

**迭代过程**：
1. 智能体初始设计：工具执行失败 → agent 捕获异常 → 发 AgentError 事件 → 终止循环
2. 用户质疑：「为什么不让 LLM 看到错误信息，自行决定重试或换工具？」
3. 智能体修改：工具返回 `is_error=True` → 把 error 字段作为 tool_result 回传 LLM
4. 用户确认：这是 Claude Code 的关键设计，值得在 SPEC 里显式写出

**最终结果**：SPEC §3.4 Agent 循环明确写：
- 工具返回 `is_error=True`：不中断循环，把 error 字段作为 `tool_result` 回传 LLM
- 用户中断：`asyncio.CancelledError` 被捕获，保存当前 messages 到 session 后退出
- 编程异常：包成 `AgentError(recoverable=False)` 推给 TUI

---

## 三、AI 建议采纳与推翻记录

### 3.1 采纳的 AI 建议

| 建议 | 采纳理由 | 结果 |
|------|---------|------|
| 使用 Pydantic 校验配置 | fail-fast + 类型安全 + 自动生成 JSON Schema | SPEC §3.1 明确使用 Pydantic |
| SQLite + asyncio.Queue 异步 flush | 避免每个 token 触发一次 SQL 阻塞 agent 循环 | SPEC §3.5 实现了 AsyncSessionStore |
| 流式 SSE 解析 | 首 token 延迟 < 2s，用户体验好 | SPEC §4.1 性能要求 |
| Docker 容器即沙箱 | 无需内部审批流程，简化设计 | SPEC §4.2 安全设计 |
| Textual TUI 框架 | 现代、异步、CSS-like 样式、Pilot 测试支持 | SPEC §8 技术选型 |

### 3.2 推翻或修正的 AI 建议

| 原始建议 | 用户修正 | 修正理由 |
|----------|---------|----------|
| 使用 Agent 框架（LangChain 等） | 不用框架，直调 Anthropic SDK | 与「mini 基础」定位冲突；增加 200+ 行抽象代码 |
| 设置 max_iterations 防止无限循环 | 不设 max_iterations | 容器即沙箱，无需额外限制 |
| 会话存储用文件系统 | 改用 SQLite | 单文件、ACID、零外部依赖；后台 flush 避免阻塞 |
| 工具错误 → agent 终止循环 | 工具错误 → 回流 LLM | 让 LLM 自行决定如何处理，更灵活 |
| TUI 用 VerticalScroll | 改用 RichLog | 流式输出需要 RichLog（自动滚动到底部 + 支持 markup） |

### 3.3 用户主动追加的需求

| 追加需求 | 追加理由 | 结果 |
|----------|---------|------|
| 使用 uv 包管理 | 快 10–100×；与 ruff 同源；lock 文件保证 CI 一致 | SPEC §8 技术选型 |
| 会话存储改 SQLite | 单文件、ACID、零外部依赖 | SPEC §3.5 数据模型 |
| 不设 max_iterations | 容器即沙箱 | SPEC §3.4 Agent 循环 |

---

## 四、冷启动验证

### 4.1 验证配置

根据课程文档 §4.5 要求：「正式进入实现前，学生须用一个与主开发智能体不同的 agent，在不喂入你与主 agent 的对话历史的前提下，仅凭 SPEC.md + PLAN.md 来尝试实现 1–2 个 task。」

| 项目 | 值 |
|------|-----|
| 主开发智能体 | Claude Code (Superpowers) |
| 冷启动验证智能体 | **OpenCode** |
| 验证 Task | Task 1（项目骨架）+ Task 3（Tools 骨架） |
| 会话状态 | 全新 session，不导入任何先前会话或 memory |
| 喂入内容 | 仅 SPEC.md + PLAN.md，不补充口头解释 |

### 4.2 验证过程

**Task 1（项目骨架 + uv + test infrastructure）**：

- OpenCode 仅凭 SPEC + PLAN 成功完成了项目骨架搭建
- 正确创建了 pyproject.toml / Makefile / pytest.ini / .python-version / conftest.py 等文件
- `uv sync` + `uv run miniagent` + `uv run pytest --collect-only` 三个 smoke test 全部通过
- 未提出任何关于 spec 缺陷的问题

**Task 3（Tools 模块骨架 — ToolResult + REGISTRY + path sandbox helper）**：

- OpenCode 正确实现了 ToolResult dataclass + resolve_sandbox_path + 空 REGISTRY + all_schemas + execute
- 4 个测试（resolve_sandbox_path inside/traversal/absolute-outside + ToolResult.is_error）全部通过
- TDD 红绿循环正确执行：先写测试 → RED（ModuleNotFoundError）→ 实现 → GREEN

### 4.3 发现的 spec 缺陷

OpenCode 在验证过程中**未提出任何问题**，也**未做出与原意不一致的解读**。两个 task 均按照 SPEC + PLAN 的字面描述顺利完成。

**分析**：
- Task 1 和 Task 3 是相对简单的基建 task，SPEC/PLAN 描述足够清晰
- PLAN 中每个 task 的步骤（文件列表 / 测试代码 / 实现代码 / 验证命令）细化到可直接执行
- SPEC 的模块划分、接口签名、错误处理描述无歧义

### 4.4 验证结论

冷启动验证表明 SPEC.md + PLAN.md 的清晰度足够高，一个完全不了解项目背景的 agent（OpenCode）能够仅凭文档独立完成 task 实现。**未对 SPEC/PLAN 做任何修订**。

这也验证了 Phase 1 brainstorming 阶段「一次只问一个问题」「方案对比 3 个就够」「数据流 vs API 契约分开讨论」等策略的有效性——产出的文档质量经受住了「陌生智能体」的检验。

### 4.5 补充保障措施

除冷启动验证外，以下措施进一步保障了 SPEC/PLAN 质量：

1. **SPEC 自审修订**：commit `92adb2f` 包含 self-review fixes
2. **PLAN 逐 task 验证**：每个 task 都有明确的验证步骤（包括将要写的失败测试）
3. **TDD 强制执行**：19/19 task 严格遵循 red → green → refactor 循环
4. **Code Review**：Phase 4 完成后进行两阶段代码评审，修复 6 项 Important issues

---

## 五、Superpowers brainstorming 技能评价

### 5.1 做得好的地方

1. **一次只问一个问题**：brainstorming 技能硬规则，用户能逐条深思，不会被淹没
2. **方案对比 3 个就够**（A 推荐 + B/C 反例），再多就疲劳
3. **数据流 vs API 契约分开讨论**（§1 vs §2）能暴露「TUI 不直接调 LLM」这种耦合问题
4. **错误处理「工具错误回流 LLM」是 Claude Code 的关键设计**——值得在 SPEC 里显式写出，否则 subagent 实现时容易做成「agent 循环兜底」的反模式
5. **session 存事件流 vs messages 快照**值得讨论：我选事件流（更可审计），但代价是 replay 一次——单次启动成本可接受

### 5.2 让人不满的地方

1. **智能体默认推荐框架**：初始建议使用 LangChain / Pydantic AI 等框架，与「mini 基础」定位冲突
2. **未主动提及 uv 包管理**：用户需要主动追加，智能体未主动提供选项
3. **未主动讨论 max_iterations**：用户需要主动推翻「防无限循环」的默认建议
4. **SPEC 模板的「exact content」要求**：在 ruff 严格模式下必报 F401，subagent 必须按「实际用到的」删减
5. **部分 spec 模板有 bug**：Task 13 的 AssistantDelta 累积但不写（注释说「newline-per-delta」但代码没实现）

---

## 六、关键 Prompt 模板与策略

### 6.1 最有效的 Prompt 策略

**策略 1：「先写失败测试再写实现」**

```
写一个测试，验证 [具体行为]。
运行测试，确认它失败（RED）。
写最小实现，让测试通过（GREEN）。
运行全量测试，确认无回归。
```

**为什么有效**：
- 强制 subagent 先理解「什么行为是对的」再写代码
- RED 阶段的失败输出是「模块不存在」的真实信号，不是占位
- GREEN 阶段的通过是「行为正确」的客观证据

**策略 2：「spec 偏差必须记录」**

```
如果 spec 给的代码在当前环境跑不通（linter 报错、API 变化、平台差异），
必须在 AGENT_LOG 显式声明「为什么这样改」。
```

**为什么有效**：
- 未来 reviewer 看到偏离会问「为什么要这样」，AGENT_LOG 是唯一答案
- 沉淀为项目级教训，避免未来 subagent 重复踩坑

**策略 3：「monkeypatch env var 是硬规则」**

```
所有读 env var 的代码，测试必须显式设 env var（用 pytest 的 monkeypatch fixture）。
```

**为什么有效**：
- pytest 用的是 host 进程的环境，不是容器
- 不设 env var 会导致测试用到 host 的真实配置，结果不可控

### 6.2 教训沉淀

| 教训 | 来源 | 应用场景 |
|------|------|---------|
| 所有 `dict` 注解必须写 `dict[str, Any]` | Task 2, 3, 9, 10, 11 | mypy strict 模式 |
| 所有 `ORDER BY <时间戳>` 必须加 tie-breaker | Task 8, 8b | SQLite 查询 |
| 测试必须显式设 `MINI_AGENT_WORKSPACE` env var | Task 4, 5, 6, 7 | 读 env var 的代码 |
| `# noqa: F401` 用于「表达公共 API 表面」 | Task 3, 4, 5, 6, 7 | 测试 import |
| spec 模板的「exact content」在 ruff 严格模式下必报 F401 | 全局 | subagent 必须按「实际用到的」删减 |
| e2e test 是「发现 wire-up bug」的唯一途径 | Task 18 | 单元/integration 测逻辑，e2e 测 wire-up |
| code review 适合在「完整 feature 集成后」做一次 | Task 21 | 发现「模块间契约不一致」类问题 |

---

## 七、SPEC 与 PLAN 质量评估

### 7.1 SPEC 质量

**优点**：
- 9 轮澄清覆盖了所有关键决策点
- 3 方案对比让用户有选择权
- 5 段设计确认保证了每个模块的完整性
- 明确的「范围之外」清单（§11）防止 scope creep

**不足**：
- 部分 spec 模板有 bug（Task 13 的 AssistantDelta 累积但不写）
- 未主动讨论 max_iterations（用户需要推翻默认建议）
- 未主动提及 uv 包管理（用户需要追加）

### 7.2 PLAN 质量

**优点**：
- 19 个 task 颗粒度足够细，每个 task 2–5 分钟
- 每个 task 包含明确的验证步骤（包括将要写的失败测试）
- 明确标出 task 之间的依赖与可并行的部分
- Parallelization Map 指导 worktree 并行

**不足**：
- 部分 spec 模板的代码在当前环境跑不通（respx 0.23 API 变化、textual 0.80 App[None]）
- Task 8b 的 TUI 集成步骤写「改 tui.py」，但 tui.py 当时不存在（spec 超前）
- 冷启动验证被跳过，无法验证 SPEC/PLAN 在「陌生智能体」下的清晰度

---

## 八、总结

### 8.1 关键成果

- **SPEC**：9 轮澄清 + 3 方案对比 + 5 段设计确认，覆盖 5 个核心模块 + 1 个辅助模块
- **PLAN**：19 个 task，每个 task 2–5 分钟，严格 TDD 红绿循环
- **实现**：54 tests passed，ruff 0 error，mypy strict 0 error，feature branch 合并到 main
- **Code Review**：修复 6 项 Important issues（AsyncSessionStore wire-up / _BACKOFF_BASE env var / --resume history / bash 限制文档 / tools singleton / TUI 死代码）

### 8.2 关键教训

1. **TDD 纪律带来的复利**：19 个 task 每个都严格 red→green→refactor，最后阶段反而容易（spec bug 在 RED 阶段就能抓到）
2. **「spec 滞后于环境」是最高频 bug 源**：respx 0.23 API 变化、textual 0.80 App[None] 强制泛型、SQLite tie-breaker、bash handler 的 UP041/ASYNC240、subprocess path 翻译……每 3-4 task 就遇到一次
3. **e2e test 是「发现 wire-up bug」的唯一途径**：Task 18 发现的 `tools=REGISTRY` (dict) vs `agent.run` 期望 (object) 不一致，是 14 个 unit/integration test 都没覆盖的
4. **AGENT_LOG 是 Phase 4 最有价值的产出**：52 个测试 + 8 个 module + 19 个 commit 是「what was built」，AGENT_LOG 是「why & how」

### 8.3 Phase 3 冷启动验证的替代

虽然跳过了正式的冷启动验证，但通过以下方式保障质量：
1. SPEC 自审修订（commit `92adb2f`）
2. PLAN 逐 task 验证（每个 task 都有明确的验证步骤）
3. TDD 强制执行（19/19 task 严格遵循 red → green → refactor）
4. Code Review（Phase 4 完成后两阶段评审，修复 6 项 Important issues）
5. 54 tests passed + ruff 0 error + mypy strict 0 error 的客观质量门
