# AI4SE Final Project

> *Spec-Driven, Subagent-Built, Human-Owned.*

本仓库是 **AI4SE 期末项目** 的工程化交付物：使用 **[Superpowers](https://github.com/obra/superpowers)** 框架，按 `brainstorming → writing-plans → subagent-driven-development → TDD → code-review → finishing-a-development-branch` 的 7 步工作流，从规约出发、由 subagent 自主执行、人类全程评审，完成一个具有一定规模的真实软件项目。

课程要求与评分细则参见 [docs/AI4SE_Final_Project0518.md](docs/AI4SE_Final_Project0518.md)。

---

## 项目状态

- [x] **Phase 0**：仓库初始化（initial commit）
- [ ] **Phase 1**：`brainstorming` → 产出 [SPEC.md](SPEC.md)
- [ ] **Phase 2**：`writing-plans` → 产出 [PLAN.md](PLAN.md)
- [ ] **Phase 3**：`spec_process.md` + 冷启动验证 → 修订 SPEC/PLAN
- [ ] **Phase 4**：`subagent-driven-development` + TDD → 实现
- [ ] **Phase 5**：两阶段评审、`finishing-a-development-branch` 收尾
- [ ] **Phase 6**：容器化、CI、可选部署
- [ ] **Phase 7**：[REFLECTION.md](REFLECTION.md) 反思报告

详细过程记录见 [AGENT_LOG.md](AGENT_LOG.md)。

---

## 目录结构

```
.
├── docs/                       # 课程原始文档
│   └── AI4SE_Final_Project0518.md
├── SPEC.md                     # 设计规约（Phase 1 产出）
├── PLAN.md                     # 实现计划（Phase 2 产出）
├── SPEC_PROCESS.md             # 协作过程文档（Phase 3 产出）
├── AGENT_LOG.md                # 智能体使用过程记录（持续维护）
├── REFLECTION.md               # 反思报告（Phase 7 产出）
├── README.md                   # 本文件
├── Dockerfile                  # 容器化镜像
├── docker-compose.yml          # 多服务编排（如适用）
├── .github/workflows/          # CI 配置
├── src/                        # 实现代码（Phase 4 起）
└── tests/                      # 测试代码
```

---

## 运行

### Quick start

```bash
# 1. Configure
mkdir -p ~/.config/mini-agent
cat > ~/.config/mini-agent/config.toml <<'EOF'
[llm]
api_key = "sk-ant-..."
base_url = "https://api.anthropic.com"
model = "claude-sonnet-4-6"
EOF

# 2. Run (uv)
uv sync --extra dev
uv run miniagent

# Or via Docker
make docker-build
docker run -it --rm -v $PWD:/workspace -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY mini-agent
```

### Useful commands

| Command | What it does |
|---|---|
| `make dev` | Install deps + launch TUI |
| `make test` | Run unit + integration tests |
| `make lint` | ruff check + format check |
| `make type` | mypy |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run TUI in container |
| `miniagent --resume <id>` | Resume a previous session |
| `miniagent --list` | Show recent sessions |

---

## 致谢

- [Superpowers](https://github.com/obra/superpowers) — Jesse Vincent 的编码智能体技能框架
- [Open Design](https://github.com/nexu-io/open-design) — 前端 / UI 项目可选依赖
