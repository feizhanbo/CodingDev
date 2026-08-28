# DevPilot V1

<p align="center">
  <em>企业研发任务 Agent：Issue → 代码修改 → 测试验证 → 自我修复 → 可评估交付</em>
</p>

DevPilot 是一个面向企业软件研发流程的**任务执行型 AI Agent**。它接收一个研发 Issue，主动分析目标代码仓库，形成实施计划，调用受控工具完成代码修改和测试，基于测试结果进行自我修复，最终输出可审查的 Git Diff 与交付报告。

> **项目定位**：学习型企业研发 Agent / Agent Engineering 实验平台  
> **技术路线**：Custom Runtime First，Framework Ready  
> **V1 运行模式**：单 Agent + 本地 Sandbox + Mock 后端仓库（ShopFlow）+ Deterministic Verifier

---

## 为什么做这个项目

DevPilot 不把"生成代码"作为唯一能力，而把**完整研发闭环**作为业务对象，重点实践 Agent Loop、Tool Calling、State、Context Engineering、Planning、Self-correction、Sandbox、Guardrails、Verifier 与 Evaluation。

V1 的目标不是尽快调用一个现成 Agent 框架，而是**亲自暴露 Agent Runtime、Tool、State、Context、Verifier、Sandbox、Eval 的真实工程边界**——这样未来引入 LangGraph / OpenAI Agents SDK 时，能真正理解框架到底解决了什么，而不是只会调用 `create_agent()` / `graph.invoke()`。

---

## 核心特性

- ✅ **完整研发闭环**：Issue → Explore → Plan → Edit → Test → Repair → Verify → Report
- ✅ **自研 Custom Runtime**：Agent Loop / State Manager / Context Builder / Loop Guard 全部自实现，未来可平滑迁移框架
- ✅ **受控 Tool System**：8 个核心工具（repo / code / test / git），无任意 shell，路径越界/forbidden 文件全程拦截
- ✅ **隔离 Sandbox**：每次运行从 baseline 仓库创建干净 workspace，不污染宿主环境
- ✅ **Deterministic Verifier**：完成状态由测试 + 策略检查驱动，不信任 LLM 自我声明
- ✅ **多 LLM 兼容**：支持 OpenAI / DeepSeek / 阿里百炼 GLM 系列等 OpenAI 兼容 API
- ✅ **鲁棒补丁应用**：`git apply` → `patch` 命令 → 纯 Python difflib 模糊匹配三级后备
- ✅ **可观测 Trace**：每次 Tool Call / Observation / State 变化落盘 JSONL，可回放
- ✅ **Eval Benchmark**：8 个标准 Issue（Feature / Bug / Performance 多类型）+ Hidden Tests 防针对性 hard-code

---

## 业务闭环

```text
Development Issue
      │
      ▼
Task Intake
      │
      ▼
Repository Exploration
      │
      ▼
Implementation Plan
      │
      ▼
Code Modification
      │
      ▼
Run Tests ───────┐
      │           │ failed
      │ passed    ▼
      │      Error Analysis
      │           │
      │      Patch / Replan
      │           │
      └───────────┘
      │
      ▼
Final Verification
      │
      ▼
Git Diff + Delivery Report
```

---

## 快速开始

### 前置依赖

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（包管理器）
- git
- [ripgrep](https://github.com/BurntSushi/ripgrep)（代码搜索）

### 安装

```bash
cd devpilot
uv sync
```

### 初始化 ShopFlow 后端

```bash
cd shopflow-order-service
uv sync
uv run python -m app.db.seed   # 初始化示例数据
```

### 运行一个 Issue

```bash
cd devpilot

# 真实 LLM（需配置 API Key）
cp .env.example .env           # 编辑填入你的 API Key / 模型 / endpoint
uv run python -m devpilot.cli run evals/issues/DEV-001.yaml

# 使用 FakeLLMClient（无需 API Key，用于确定性测试与 Runtime 联调）
uv run python -m devpilot.cli run evals/issues/DEV-001.yaml --fake
```

### 批量评估

```bash
# 单个 Issue
uv run python -m devpilot.cli eval DEV-001 --fake

# 全部 Issue
uv run python -m devpilot.cli eval --all --fake
```

### 查看运行结果

```bash
uv run python -m devpilot.cli inspect <run-id>   # 查看某次 run 详情
uv run python -m devpilot.cli diff <run-id>      # 查看 Agent 产出的 diff
```

---

## 总体架构

```text
┌─────────────────────────────────────────────────┐
│                    DevPilot CLI                  │
└───────────────────────┬─────────────────────────┘
                        │ DevelopmentTask
                        ▼
┌─────────────────────────────────────────────────┐
│                  Agent Runtime                   │
│   Loop │ State Manager │ Context Builder │ Guard │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
                 ┌───────────────┐
                 │DeveloperAgent │
                 └───────┬───────┘
                         │ LLM decision / tool call
                         ▼
                 ┌───────────────┐
                 │ Tool Registry │（8 个核心工具）
                 └───┬───┬───┬───┘
                     ▼   ▼   ▼
              Repo Tools │ Code Tools │ Test/Git Tools
                     └───────┬───────┘
                             ▼
                    Sandbox Workspace
                             │
                             ▼
                  ShopFlow Git Repository
                             │
                             ▼
                     Final Verifier
                             │
                             ▼
                     Diff + Run Report
```

### 核心组件职责

| 组件 | 职责 | 框架无关 |
|------|------|:--------:|
| DeveloperAgent | 决定下一步，输出 Tool Call / Finish Intent | 是 |
| AgentRuntime | 循环、状态推进、重试、停止、超时、策略执行 | Runtime 实现层 |
| ContextBuilder | 将 Task/Plan/相关文件/Observation 组装为模型上下文 | 是（需 Adapter） |
| ToolRegistry | 注册、Schema 暴露、Tool Dispatch | 是 |
| SandboxWorkspace | 隔离代码修改，限制路径 | 是 |
| TaskVerifier | pytest / 策略检查（diff 非空 / forbidden / 文件数） | 是 |
| EvalRunner | 重置仓库、执行 Agent、跑 hidden tests、收集指标 | 是 |
| LLMClient | 统一模型调用接口（OpenAI / DeepSeek / GLM） | 是 |

### Tool 清单

| Tool | 输入 | 输出 | 底层实现 |
|------|------|------|----------|
| `repo.list_files` | path, depth | 文件/目录列表 | pathlib |
| `repo.search_code` | query, path, glob | 匹配文件与行 | ripgrep + Python fallback |
| `repo.read_file` | path, start_line, end_line | 带行号文本 | pathlib（上限 500 行） |
| `code.apply_patch` | unified diff | 修改结果/失败原因 | git apply → patch → Python difflib 三级后备 |
| `code.create_file` | path, content | 创建结果 | pathlib，受 Sandbox 限制 |
| `test.run` | target, args | stdout/stderr/exit_code/summary | pytest 子进程（带超时） |
| `git.diff` | path? | unified diff | git diff |
| `git.status` | 无 | 修改文件状态 | git status --porcelain |

> **为什么不开通用 Shell？** V1 不提供 `shell(command)` 是有意设计。Agent 的能力由明确 Tool 决定，Runtime 可对每个工具做参数校验、路径约束、超时、日志与权限策略，避免把宿主 shell 直接暴露给模型。

---

## Issue 数据集

8 个标准研发 Issue 覆盖 Feature / Bug / Performance 多类型与多难度：

| Issue | 类型 | 目标 | 难度 |
|-------|------|------|:----:|
| DEV-001 | Feature | 订单列表增加 status filter | ★ |
| DEV-002 | Bug | 禁止 shipped/completed 订单取消 | ★ |
| DEV-003 | Bug | 订单分页边界修复 | ★★ |
| DEV-004 | Bug | percentage coupon 计算错误 | ★★ |
| DEV-005 | Performance | 订单详情 N+1 Query | ★★★ |
| DEV-006 | Feature | Email 规范化 | ★★ |
| DEV-007 | Bug | 防止重复支付 | ★★★ |
| DEV-008 | Feature | Order audit fields | ★★★ |

典型 Agent 行为：`search_code("orders")` → `read_file(router/service/repository/tests)` → 形成 Plan → `apply_patch` → `run_tests` → 据失败结果修复 → `git_diff` → Verifier。

---

## ShopFlow 后端

[shopflow-order-service](file:///d:/devpilot/shopflow-order-service) 是 DevPilot 的**目标代码仓库**，用于制造真实但规模可控的企业后端研发任务。

- **技术栈**：FastAPI + SQLAlchemy 2.x + SQLite + Pydantic + pytest
- **领域模型**：Customer / Product / Order / OrderItem / Coupon（`Order.status`：pending/paid/shipped/completed/cancelled）
- **严格分层**：API（`app/api/`）→ Service（`app/services/`）→ Repository（`app/repositories/`）→ DB（`app/db/`）
- **API 范围**：customers / products / orders / coupons 共 9 个端点
- **完整测试基线**：`tests/api/`、`tests/repositories/`、`tests/services/` 全量覆盖

设计原则：项目规模控制在 Agent 可逐步探索的范围，不把全部代码一次塞入 Context；每个 Issue 只改变有限模块，便于评测修改范围；**Visible Tests** 用于开发反馈，**Hidden Tests** 用于防止针对性 hard-code。

---

## 项目结构

```text
devpilot/
├── devpilot/                    # DevPilot Agent 主包
│   ├── domain/                  # 领域模型（Task / State / Plan / Decision / Result）
│   ├── agents/                  # DeveloperAgent
│   ├── runtime/
│   │   ├── base.py              # RuntimeConfig
│   │   └── custom/             # 自研 Runtime（runner / loop_guard / context / state_manager）
│   ├── tools/                   # 8 工具 + Registry + PathGuard
│   ├── workspace/              # SandboxWorkspace
│   ├── verification/           # TaskVerifier
│   ├── llm/                    # LLMClient / OpenAI / Fake / prompts
│   ├── tracing/               # TraceWriter / events / metrics
│   └── cli.py                 # CLI（run / inspect / diff / eval）
├── evals/
│   ├── runner.py               # EvalRunner
│   ├── metrics.py             # 指标收集
│   ├── issues/                # DEV-001~008 YAML
│   └── hidden_tests/         # 隐藏测试
├── shopflow-order-service/     # Mock 后端目标仓库
├── tests/                      # 单测 + 集成 + E2E
└── pyproject.toml
```

---

## 测试

```bash
# DevPilot 自身测试
cd devpilot
uv run pytest

# ShopFlow 基线测试
cd shopflow-order-service
uv run pytest
```

### 测试策略

DevPilot 的测试分两层：

1. **基础设施确定性测试**：Tool Registry 重复注册、Path Guard 越界、Patch 合法/失配、Test Tool pass/fail/timeout、Loop Guard max_steps/retry、State Manager phase 迁移、Verifier 各分支——用 `FakeLLMClient` 固定输出测 Runtime 的 determinism。
2. **Agent 行为评估**：用真实 LLM 跑 Issue，多次重放并统计成功率/步数/Token，衡量模型驱动行为的稳定性。两者不能互相替代。

---

## 配置

见 `devpilot/.env.example`，主要配置项：

```dotenv
DEVPILOT_API_KEY=...               # LLM API Key
DEVPILOT_MODEL=...                 # 模型名（如 glm-5.2 / deepseek-v4-flash）
DEVPILOT_BASE_URL=...              # OpenAI 兼容 endpoint
DEVPILOT_MAX_STEPS=80              # 最大 Agent 步数
DEVPILOT_MAX_TEST_RETRIES=5        # 最大测试修复重试
DEVPILOT_MAX_MODIFIED_FILES=10     # 最大修改文件数
DEVPILOT_MAX_PATCH_FAILURES=3      # 最大 patch 失败次数
DEVPILOT_TEST_TIMEOUT_SECONDS=120  # 单次测试超时
DEVPILOT_NETWORK_ACCESS=false      # 网络访问（默认关闭）
DEVPILOT_WORKSPACE_ROOT=./workspaces
DEVPILOT_RUNS_ROOT=./runs
DEVPILOT_BASE_REPO=../shopflow-order-service
```

---

## 已知限制（V1）

- 使用自研 Custom Runtime（尚未接入 LangGraph / OpenAI Agents SDK）
- 不自动 Git commit / push（保留人工确认边界）
- 无 GitHub / Jira Issue API（采用 YAML/Markdown Task Adapter）
- 无 Multi-Agent（先验证单 Agent 职责边界）
- 无网络访问（保证 Eval 可重复、安全）
- 无生产部署（V1 目标是本地实验与工程基线）
- 无长期记忆（只做 Run State，不引入向量库）
- 无 Web UI（CLI only）

---

## 后续路线图

```text
V1    Issue → Code → Test → Repair → Verify
V1.1  Context compaction + Better planning
V1.2  Eval dashboard + regression benchmark
V2    GitHub Issue → Branch → PR + Human approval
V3    Project knowledge / RAG / Engineering memory
V4    Review Agent
V5    Framework Runtime（LangGraph）+ durable state
V6    Multi-Agent R&D Supervisor
V7    Logs / Metrics / Incident / SRE Agent
```

---

## 文档

- 📐 [DevPilot V1 详细开发设计文档](file:///d:/devpilot/DevPilot_V1_详细开发设计文档.md) — 完整架构、Domain Model、Runtime、Tool、Sandbox、Verifier、Eval 与 Milestone 拆解
- 📊 [当前开发实施详细进度文档](file:///d:/devpilot/CURRENT_DEV_PROGRESS.md) — 逐模块实现深度、已完成能力、DEV-001 卡点根因与后续阶段建议
- 📖 [DevPilot English README](file:///d:/devpilot/devpilot/README.md) — 英文版快速上手

---

## 设计原则摘要

> **硬规则**：LLM 可以"请求完成"，但 Runtime 才能"确认完成"。完成状态必须由 Deterministic Verifier 驱动。

- **先获取证据再改代码**：不允许凭文件名猜测实现。
- **最小修改**：避免与 Issue 无关的重构，每个改动应能映射到 acceptance criteria。
- **测试失败先读错误**：不盲目重复 `run_tests`，先分析失败信息再修复。
- **可演进**：业务层 Tool / Verifier / Domain / Sandbox / Eval 不依赖具体 Runtime，未来切换框架时尽量不变。

---

*DevPilot V1 — 把"决策 → 工具 → 观察 → 状态 → 验证"这一条链真正做扎实。*
