# TUI 美化设计规约

> **日期**：2026-06-13
> **范围**：Mini Coding Agent TUI 的终端视觉与交互体验升级
> **方案**：方案 B — TUI 全面美化 + 小改下层透传 usage
> **约束**：暗色系硬编码，不引入可配置主题系统（YAGNI）

---

## 1. 目标

将 miniagent 的 TUI 从"功能可用"提升到"视觉精致"，具体包括：

1. 统一的暗色色彩体系（Catppuccin Mocha 色调）
2. 面板式消息展示（user / assistant / tool 三种样式）
3. 信息丰富的 header（token 用量 + 耗时）
4. 带 spinner 的状态栏（thinking / calling tool / idle）
5. Token 用量从 API → agent → TUI 的完整透传

---

## 2. 色彩体系

基于 Catppuccin Mocha 调色板，用 Textual CSS 变量定义：

| 用途 | 变量名 | 色值 | 说明 |
|---|---|---|---|
| 背景 | `$surface` | `#1e1e2e` | 主背景，深蓝灰 |
| 面板背景 | `$surface-light` | `#313244` | 消息面板、header/status |
| 主文字 | `$text` | `#cdd6f4` | 默认文字色 |
| 次要文字 | `$text-muted` | `#a6adc8` | 时间戳、session ID |
| 用户强调 | `$accent-cyan` | `#89dceb` | `you>` 标签 |
| 助手强调 | `$accent-green` | `#a6e3a1` | `assistant>` 标签 |
| 工具强调 | `$accent-mauve` | `#cba6f7` | 工具调用 |
| 成功 | `$success` | `#a6e3a1` | ✓ |
| 错误 | `$error` | `#f38ba8` | ✗ |
| 边框 | `$border` | `#585b70` | 面板边框 |

CSS 从内联 `CSS = """..."""` 改为独立的 `tui.css` 文件，通过 `CSS_PATH` 引用。

---

## 3. 消息展示（面板式）

三种消息类型各有独立视觉样式，均使用 Rich `Panel` 包裹。

### 3.1 用户消息

```
╭─ you ──────────────────────────────────────╮
│ 帮我读一下 config.toml 的内容               │
╰────────────────────────────────────────────╯
```

- 标题栏：`you`，青色（`$accent-cyan`），左对齐
- 边框：青色细线（`ASCII` 或 `ROUNDED`）
- 内容：普通文本，左对齐

### 3.2 助手消息

```
╭─ assistant ────────────────────────────────╮
│ 好的，我来读取配置文件。                     │
│                                            │
│ 这是返回的内容...                            │
╰────────────────────────────────────────────╯
```

- 标题栏：`assistant`，绿色（`$accent-green`）
- 边框：绿色细线
- 内容：支持 Rich markup（代码块使用 `Syntax` 高亮）

### 3.3 工具调用 + 结果（两个紧邻面板）

`ToolCallStart` 和 `ToolCallResult` 是两个独立事件，`RichLog` 不支持回溯更新。渲染策略：

**工具调用面板**（`ToolCallStart` 事件触发）：
```
╭─ 🔧 read_file ─────────────────────────────╮
│ {"path": "config.toml"}                    │
╰────────────────────────────────────────────╯
```
- 标题栏：`🔧 tool_name`，紫色（`$accent-mauve`）
- 内容：JSON 格式的参数（灰色小字）

**工具结果面板**（`ToolCallResult` 事件触发）：
```
╭────────────────────────────────────────────╮
│ ✓ api_key = "sk-..."                       │
│ base_url = "https://api.deepseek.com/..."  │
╰────────────────────────────────────────────╯
```
- 无标题，紧凑面板
- 成功：绿色 `✓` + 输出
- 失败：红色 `✗` + 错误信息
- 输出超过 5 行时，折叠显示前 3 行 + `[... N more lines]`（按 `\n` 分割计数）

两个面板视觉上紧邻，形成一个完整的工具调用-结果块。

### 3.4 历史回放

`--resume` 加载的历史消息使用同样的面板样式，保持视觉一致。

---

## 4. Header & Status Bar

### 4.1 Header（顶部，单行，左右分区）

```
 ● miniagent · deepseek-v4-flash · a3f2b1c4    tokens: 1.2k / 340 · 2.3s
```

- 左侧：应用名 + 模型名 + session ID 前 8 位
- 右侧：token 用量（input / output）+ 本轮耗时，实时更新
- 背景 `$surface-light`，文字 `$text-muted`，应用名加粗
- 无 token 数据时（首轮输入前），右侧显示 `ready`

### 4.2 Status Bar（底部，输入框上方）

```
 ⠹ thinking...                          /exit · /reset · Ctrl+C
```

- 左侧：spinner + 状态描述
  - `ready` → 空闲，无 spinner
  - `⠋ thinking...` → LLM 思考中
  - `⠹ calling read_file...` → 工具执行中（显示工具名）
  - `⠸ interrupted` → 用户取消
- 右侧：快捷键提示（固定文本，灰色小字）
- Spinner 用 `set_interval(0.08)` 逐帧切换 braille 字符 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`

---

## 5. Token 用量透传（llm → agent → tui）

唯一需要改下层接口的部分，三个小改动：

### 5.1 llm.py：捕获 usage

在 `_stream_step_once` 的 SSE 解析循环中：

- `message_start` 事件：提取 `usage.input_tokens`
- `message_delta` 事件（流末尾）：提取 `usage.output_tokens`

新增 `StepUsage` dataclass：

```python
@dataclass
class StepUsage:
    input_tokens: int
    output_tokens: int
```

返回值从 `tuple[str, list[ToolCall]]` 改为 `tuple[str, list[ToolCall], StepUsage]`。

如果 API 未返回 usage（兼容性），默认 `StepUsage(0, 0)`。

`stream_step` 的 retry 包装层也同步更新返回类型。

### 5.2 agent.py：新增事件字段

`EndTurn` 新增两个字段：

```python
@dataclass
class EndTurn:
    final_text: str
    input_tokens: int = 0
    output_tokens: int = 0
```

`run()` 循环中把 `StepUsage` 透传到 `EndTurn`。

`LLMProtocol` 的 `stream_step` 返回类型更新为 `tuple[str, list[Any], Any]`（第三项为 usage）。

### 5.3 tui.py：消费 usage

- `_render_event` 中 `EndTurn` 分支更新 header 右侧显示
- 记录 `_turn_start_time: float`，`EndTurn` 时计算耗时
- `_set_header_right(tokens_in, tokens_out, elapsed)` 格式化显示

---

## 6. 实现文件清单

| 文件 | 改动类型 | 改动量 |
|---|---|---|
| `src/miniagent/tui.py` | 重写 | 大（CSS + widget + 渲染逻辑 + spinner） |
| `src/miniagent/tui.css` | 新建 | 中（完整 CSS 样式表） |
| `src/miniagent/agent.py` | 小改 | 小（EndTurn 加字段，run() 透传 usage） |
| `src/miniagent/llm.py` | 小改 | 小（SSE 解析 + StepUsage + 返回类型） |
| `tests/unit/test_agent.py` | 更新 | 小（EndTurn 断言加 usage 字段） |
| `tests/unit/test_llm.py` | 更新 | 小（mock SSE 补 message_delta） |
| `tests/integration/test_tui.py` | 更新 | 小（适配新 widget ID / 结构） |

---

## 7. 不做的事项

- ❌ 可配置主题系统（YAGNI，v1 暗色硬编码即可）
- ❌ 代码块语法高亮的自动语言检测（Rich Syntax 已内置，不需要额外逻辑）
- ❌ 消息折叠/展开的点击交互（Textual 的 Static 不支持点击事件，v1 用行数截断即可）
- ❌ 多面板/分屏布局（保持单面板滚动对话）
- ❌ 输入框的样式美化（保持 Textual 默认，已足够清晰）

---

## 8. 验收标准

1. `make test` 全部通过（54 tests，允许新增测试）
2. `make lint` 无 error
3. `make type` 无 error
4. 手动启动 `uv run miniagent`，视觉效果符合 §2-§4 设计
5. Header 右侧实时显示 token 用量和耗时
6. Status bar spinner 在 LLM 思考和工具执行时正确动画
