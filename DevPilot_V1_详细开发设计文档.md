# DevPilot V1

**企业研发任务 Agent 详细开发设计文档**

从 Issue → 代码修改 → 测试验证 → 自我修复 → 可评估交付

版本：V1.0  
定位：学习型企业研发 Agent / Agent Engineering 实验平台  
技术路线：Custom Runtime First，Framework Ready

# 文档信息

| **字段**    | **内容**                                                                        |
|-------------|---------------------------------------------------------------------------------|
| 文档名称    | DevPilot V1 企业研发任务 Agent 详细开发设计文档                                 |
| 项目代号    | DevPilot                                                                        |
| 当前版本    | V1.0                                                                            |
| 目标读者    | 项目开发者、Agent 工程学习者、代码评审者                                        |
| 主要目标    | 构建一个可运行、可验证、可评估、可演进的研发任务执行 Agent                      |
| V1 运行模式 | 单 Agent + 本地 Sandbox + Mock 后端仓库 + Deterministic Verifier                |
| 未来演进    | GitHub/Jira、持久化 State、Human Approval、框架 Runtime、Multi-Agent、SRE Agent |

> **核心原则：**V1 的目标不是尽快调用一个现成 Agent 框架，而是掌握 Agent Runtime、Tool、State、Context、Verifier、Sandbox、Eval 的真实工程边界。

# 目录

1. 项目背景与目标

2. V1 业务范围与边界

3. 业务场景与用户故事

4. 功能需求与非功能需求

5. 配套模拟后端 ShopFlow

6. DevPilot V1 总体架构

7. 分层与依赖原则

8. Domain Model 设计

9. Custom Agent Runtime 设计

10. Developer Agent 设计

11. Tool System 设计

12. Workspace Sandbox 与安全边界

13. Context Engineering 与 Prompt 设计

14. Verification 与停止条件

15. Trace / Observability

16. Eval 与 Issue Dataset

17. CLI 与运行流程

18. 项目目录结构

19. 开发阶段与任务拆解

20. 测试策略

21. 框架升级与迁移策略

22. 风险、限制与后续路线图

附录 A. V1 Issue Dataset

附录 B. Tool 接口草案

附录 C. 配置项建议

附录 D. Definition of Done

# 1. 项目背景与目标

## 1.1 项目背景

DevPilot 是一个面向企业软件研发流程的任务执行型 Agent。它接收一个研发 Issue，主动分析目标代码仓库，形成实施计划，调用受控工具完成代码修改和测试，并基于测试结果进行自我修复，最终输出可审查的 Git Diff 与交付报告。

项目不把“生成代码”作为唯一能力，而把完整研发闭环作为业务对象。重点实践 Agent Loop、Tool Calling、State、Context Engineering、Planning、Self-correction、Sandbox、Guardrails、Verifier 和 Evaluation。

## 1.2 V1 核心目标

- 用一个可验证的真实业务闭环学习 Agent Runtime，而不是停留在聊天或代码补全。

- 构建单 Agent 的完整执行链：Issue → Explore → Plan → Edit → Test → Repair → Verify → Report。

- 所有外部动作必须通过 Tool Registry 进入受控执行环境。

- 通过 Mock Repository + Visible Tests + Hidden Tests 建立可重复 Benchmark。

- 业务层与 Runtime 层解耦，为未来替换 LangGraph / OpenAI Agents SDK 等 Runtime 做准备。

## 1.3 成功标准

| **维度** | **V1 成功标准**                                                           |
|----------|---------------------------------------------------------------------------|
| 端到端   | 至少 5 个标准 Issue 可从任务输入运行到最终结果输出                        |
| 可验证   | 最终状态不由 LLM 单方面声明，必须通过测试/策略检查                        |
| 可追踪   | 每次 Tool Call、Observation、State 变化可追踪                             |
| 可隔离   | Agent 只能修改运行 Workspace，不可修改宿主敏感路径                        |
| 可评估   | 同一 Issue 可重复运行，并产出 Task Success、Steps、Tokens、Retries 等指标 |
| 可演进   | 未来切换 Runtime 时 Tool、Verifier、Domain、Sandbox 尽量不变              |

# 2. V1 业务范围与边界

## 2.1 V1 业务闭环

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

## 2.2 V1 包含

- 自然语言/结构化 Issue 输入

- 代码仓库浏览与文本搜索

- 基于上下文的实施计划

- 受控 Patch 修改

- pytest 执行

- 失败结果回灌与自我修复

- Git Diff/Status

- Deterministic Final Verifier

- JSON/JSONL Trace

- Issue Eval Runner

## 2.3 V1 不包含

| **能力**               | **V1 决策** | **原因**                                |
|------------------------|-------------|-----------------------------------------|
| 自动 Git Commit / Push | 不做        | 先保留人工确认边界                      |
| 自动创建 PR            | 不做        | V2 接入 GitHub 时实现                   |
| Jira/GitHub Issue API  | 不做        | V1 采用 YAML/JSON/Markdown Task Adapter |
| Long-term Memory       | 不做        | V1 只做 Run State，不引入向量库         |
| Multi-Agent            | 不做        | 先验证单 Agent Runtime 与职责边界       |
| 任意 Shell Tool        | 不做        | 避免模型获得过宽系统权限                |
| 网络访问               | 默认关闭    | 保证可重复、安全的 Eval                 |
| 生产部署               | 不做        | V1 目标是本地实验与工程基线             |

# 3. 业务场景与用户故事

## 3.1 核心用户故事

| **ID** | **用户故事**                                                     | **验收要点**                                               |
|--------|------------------------------------------------------------------|------------------------------------------------------------|
| US-01  | 作为开发者，我希望给 DevPilot 一个 Issue，让它自动定位相关代码。 | Agent 使用 Repo Tools 获取上下文，不要求用户手工提供文件。 |
| US-02  | 作为开发者，我希望 Agent 在修改前先形成实施计划。                | 计划包含步骤、目标文件/模块和验证方式。                    |
| US-03  | 作为开发者，我希望 Agent 修改后自动运行测试。                    | 测试命令由受控 Test Tool 执行。                            |
| US-04  | 作为开发者，我希望测试失败时 Agent 能读取失败信息并修复。        | 至少支持有限次数的 repair loop。                           |
| US-05  | 作为开发者，我希望最终看到明确 Diff 和结果摘要。                 | 输出修改文件、测试结果、风险和建议提交信息。               |
| US-06  | 作为维护者，我希望能够复盘每一步行为。                           | 保存 Tool Call、Tool Result、Phase、Step、错误。           |
| US-07  | 作为评测者，我希望同一 Issue 能多次重放。                        | 每次使用干净 Workspace；Hidden Tests 独立执行。            |

## 3.2 示例 Issue：DEV-001

```yaml
id: DEV-001
title: Support order status filter
description: |
  订单列表接口需要支持 status 查询条件。
acceptance_criteria:
  - GET /orders?status=paid 仅返回 paid 订单
  - 非法 status 返回 HTTP 400
  - 不传 status 时保持当前行为
  - 必须新增测试
constraints:
  - API response schema 不允许变化
```

典型 Agent 行为：search_code("orders") → read_file(router/service/repository/tests) → 形成 Plan → apply_patch → run_tests → 根据失败结果修复 → git_diff → verifier。

# 4. 功能需求与非功能需求

## 4.1 功能需求

| **ID** | **需求**                                                     | **优先级** |
|--------|--------------------------------------------------------------|------------|
| FR-01  | 接收 DevelopmentTask，并初始化独立运行 Workspace             | P0         |
| FR-02  | Agent 可通过 Tool 探索代码仓库                               | P0         |
| FR-03  | Agent 形成并维护实施 Plan                                    | P0         |
| FR-04  | Agent 通过受控 Patch 修改代码                                | P0         |
| FR-05  | Agent 可运行目标测试或完整测试                               | P0         |
| FR-06  | 测试失败时支持有限次数 Self-correction                       | P0         |
| FR-07  | 输出 Git Diff、测试结果与开发摘要                            | P0         |
| FR-08  | 记录完整 Run Trace 和 Final State                            | P0         |
| FR-09  | 支持批量运行 Eval Issue                                      | P1         |
| FR-10  | 支持 Resume 的 State Schema（V1 可先只保存，不要求正式恢复） | P1         |

## 4.2 非功能需求

| **类别** | **要求**                                                           |
|----------|--------------------------------------------------------------------|
| 安全     | 只能访问 Workspace；禁止 .env、SSH、宿主系统目录；禁止任意 shell。 |
| 可重复   | Issue 每次从同一基线仓库创建干净 Workspace。                       |
| 可观测   | 每一步必须有 step_id、tool、duration、success/error。              |
| 可测试   | Tool、Runtime、Verifier 均可单测；Eval 可独立执行。                |
| 可扩展   | Tool/Runtime/LLM 通过自有抽象解耦。                                |
| 性能     | V1 优先正确性；单个小型 Issue 建议控制在 max_steps 30 内。         |
| 可靠     | 测试和 Verifier 决定完成状态，不信任 LLM 自我声明。                |

# 5. 配套模拟后端 ShopFlow

## 5.1 项目定位

ShopFlow Order Service 是 DevPilot 的目标代码仓库，用于制造真实但规模可控的企业后端研发任务。V1 推荐 Python 3.12 + FastAPI + SQLAlchemy 2.x + SQLite + Pydantic + pytest。

## 5.2 领域模型

| **实体**  | **关键字段**                                      | **说明**   |
|-----------|---------------------------------------------------|------------|
| Customer  | id, name, email                                   | 下单客户   |
| Product   | id, name, price, stock                            | 商品与库存 |
| Order     | id, customer_id, status, total_amount, created_at | 订单主数据 |
| OrderItem | id, order_id, product_id, quantity, unit_price    | 订单明细   |
| Coupon    | id, code, discount_type, discount_value           | 优惠券     |

Order.status 枚举：pending / paid / shipped / completed / cancelled。

## 5.3 API 范围

```text
GET    /customers/{id}
GET    /products
GET    /products/{id}
POST   /orders
GET    /orders
GET    /orders/{id}
POST   /orders/{id}/pay
POST   /orders/{id}/cancel
POST   /coupons/validate
```

## 5.4 推荐目录

```text
shopflow-order-service/
├── app/
│   ├── main.py
│   ├── api/{orders,products,customers}.py
│   ├── models/{order,product,customer}.py
│   ├── schemas/{order,product}.py
│   ├── services/{order_service,pricing_service}.py
│   ├── repositories/{order_repository,product_repository}.py
│   └── db/{database,seed}.py
├── tests/
│   ├── api/
│   ├── services/
│   └── repositories/
├── pyproject.toml
└── README.md
```

## 5.5 设计原则

- 项目规模控制在 Agent 可逐步探索的范围，不把全部代码一次塞入 Context。

- 保留典型企业分层：API → Service → Repository → DB。

- 每个 Issue 只改变有限模块，便于评测修改范围。

- 刻意放置 Feature / Bug / Performance 等多类任务。

- Visible Tests 用于开发反馈；Hidden Tests 用于防止针对性 hard-code。

# 6. DevPilot V1 总体架构

```text
┌─────────────────────────────────────────────────────────┐
│                     DevPilot CLI                        │
└───────────────────────┬─────────────────────────────────┘
                        │ DevelopmentTask
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    Agent Runtime                        │
│  Loop │ State Manager │ Context Builder │ Guardrails   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
                 ┌───────────────┐
                 │ DeveloperAgent│
                 └───────┬───────┘
                         │ LLM decision / tool call
                         ▼
                 ┌───────────────┐
                 │ Tool Registry │
                 └───┬────┬───┬──┘
                     │    │   │
             ┌───────┘    │   └────────┐
             ▼            ▼            ▼
        Repo Tools     Code Tools   Test/Git Tools
             └────────────┬────────────┘
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

## 6.1 核心组件职责

| **组件**         | **职责**                                                 | **是否框架无关** |
|------------------|----------------------------------------------------------|------------------|
| DeveloperAgent   | 根据当前上下文决定下一步，输出 Tool Call / Finish Intent | 是               |
| AgentRuntime     | 循环、状态推进、重试、停止、超时、策略执行               | Runtime 实现层   |
| ContextBuilder   | 将 Task/Plan/相关文件/Observation 组装为模型上下文       | 是，需 Adapter   |
| ToolRegistry     | 注册、Schema 暴露、Tool Dispatch                         | 是               |
| SandboxWorkspace | 隔离代码修改，限制路径                                   | 是               |
| TaskVerifier     | pytest/ruff/hidden tests/策略检查                        | 是               |
| EvalRunner       | 重置仓库、执行 Agent、跑 hidden tests、收集指标          | 是               |
| LLMClient        | 统一模型调用接口                                         | 是               |

# 7. 分层与依赖原则

## 7.1 推荐分层

```text
Domain Layer
  DevelopmentTask / DevPilotState / Plan / Result
        ▲
        │
Business Capabilities
  Tools / Sandbox / Verifier / Eval
        ▲
        │
Runtime Abstraction
  AgentRunner / ContextBuilder / StateStore
        ▲
        │
Runtime Implementations
  custom/   (V1)
  langgraph/ (future)
  openai_agents/ (future)
```

## 7.2 三条硬性依赖原则

1.  Tool 的真实业务实现不得写死为某个 Agent 框架的 Tool 类型；框架接入通过 Adapter 完成。

2.  DevPilotState 是业务层的 Source of Truth，不直接把框架 State 当核心领域模型。

3.  Verifier、Sandbox、Eval 不能依赖 Custom Runtime 内部实现，否则未来迁移 Runtime 会变成整体重写。

> **为什么这样做：**未来迁移到 LangGraph / OpenAI Agents SDK 时，主要重写“控制流表达”和 Adapter，而不是重写 Repo Tool、Test Tool、Sandbox、Verifier 与 Issue Dataset。

# 8. Domain Model 设计

## 8.1 DevelopmentTask

```python
class DevelopmentTask(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    constraints: list[str] = []
    metadata: dict[str, Any] = {}
```

## 8.2 Plan / PlanStep

```python
class PlanStep(BaseModel):
    id: int
    description: str
    status: Literal['pending', 'running', 'completed', 'failed', 'skipped']
    verification_hint: str | None = None

class ImplementationPlan(BaseModel):
    goal: str
    steps: list[PlanStep]
    revision: int = 1
```

## 8.3 Observation

```python
class Observation(BaseModel):
    step_id: int
    source: Literal['tool', 'runtime', 'verifier']
    name: str
    success: bool
    summary: str
    data: dict[str, Any] | None = None
    duration_ms: int | None = None
```

## 8.4 DevPilotState

```python
class DevPilotState(BaseModel):
    run_id: str
    task: DevelopmentTask
    phase: Literal[
        'understanding', 'exploring', 'planning',
        'implementing', 'verifying', 'completed', 'failed'
    ]
    plan: ImplementationPlan | None = None
    observations: list[Observation] = []
    modified_files: list[str] = []
    test_runs: list[TestRun] = []
    current_step: int = 0
    total_steps: int = 0
    retry_count: int = 0
    completion_requested: bool = False
```

## 8.5 AgentDecision

```python
class ToolAction(BaseModel):
    tool: str
    arguments: dict[str, Any]

class FinishIntent(BaseModel):
    summary: str
    risk: Literal['low', 'medium', 'high']

class AgentDecision(BaseModel):
    action: ToolAction | None = None
    finish: FinishIntent | None = None
    plan_update: ImplementationPlan | None = None
```

# 9. Custom Agent Runtime 设计

## 9.1 Runtime 的职责边界

- 初始化 Run 与 Workspace。

- 维护 DevPilotState 和阶段状态。

- 构造 Context 并调用 Agent。

- 验证 AgentDecision 是否符合 Schema 与 Policy。

- 通过 ToolRegistry 执行 Tool。

- 记录 Observation 与 Trace。

- 控制 max_steps / retry / timeout / 重复动作。

- Agent 请求完成时触发 Final Verifier。

- Verifier 通过才真正 Completed，否则继续或 Failed。

## 9.2 最小 Runner 接口

```python
class AgentRunner(Protocol):
    async def run(
        self,
        agent: Agent,
        task: DevelopmentTask,
    ) -> AgentRunResult:
        ...
```

## 9.3 Custom Runtime 伪代码

```python
async def run(task):
    state = state_factory.create(task)
    workspace = sandbox.create(state.run_id)

    while state.total_steps < config.max_steps:
        context = context_builder.build(state, workspace)
        decision = await developer_agent.decide(context)

        policy.validate_decision(decision, state)

        if decision.finish:
            verification = await verifier.verify(task, workspace, state)
            state.add(verification)
            if verification.success:
                state.phase = 'completed'
                return build_result(state, workspace)
            continue

        result = await tool_registry.execute(
            decision.action,
            ToolContext(workspace=workspace, state=state)
        )
        state.apply(result)
        loop_guard.inspect(state, decision, result)

    state.phase = 'failed'
    raise MaxStepsExceeded()
```

## 9.4 Phase State Machine

```text
understanding
      │
      ▼
 exploring ───────────────┐
      │                   │ need more context
      ▼                   │
  planning                │
      │                   │
      ▼                   │
implementing ◄────────────┘
      │
      ▼
 verifying ── failed ──► implementing / replanning
      │ passed
      ▼
 completed

Any phase ── unrecoverable / budget exceeded ──► failed
```

## 9.5 Loop Guard

| **规则**           | **建议默认值** | **行为**                             |
|--------------------|----------------|--------------------------------------|
| 最大步骤数         | 30             | 超过则 Failed                        |
| 最大测试修复重试   | 3              | 超过后停止继续自动修复               |
| 连续相同 Tool Call | 3 次           | 注入重复动作提示；再次重复则失败     |
| 单次 Test Timeout  | 120 秒         | 中断 Tool 并返回 timeout Observation |
| 最大修改文件数     | 10             | 超出需停止或人工确认                 |
| 最大 Patch 失败    | 3              | 要求重新读取文件并重建 patch         |

# 10. Developer Agent 设计

## 10.1 Agent 与 Runtime 的区别

| **对象**       | **负责**                                            | **不负责**                           |
|----------------|-----------------------------------------------------|--------------------------------------|
| DeveloperAgent | 理解任务、决定下一步、选择 Tool、提出 Plan/Finish   | 真实执行权限、路径安全、最终完成判定 |
| AgentRuntime   | 执行控制、Tool Dispatch、状态、策略、停止、Verifier | 具体研发判断与代码方案               |

## 10.2 Agent Modes

- Understanding Mode：提取目标、验收条件、约束。

- Exploration Mode：主动查找相关代码、测试和项目规范。

- Planning Mode：生成最小可执行计划和验证方式。

- Implementation Mode：按需读取文件、生成 Patch。

- Verification Mode：读取测试结果、判断是否修复/重规划/结束。

## 10.3 Agent 基础原则

- 先获取证据再改代码：不允许凭文件名猜测实现。

- 尽量最小修改：避免与 Issue 无关的重构。

- 每个关键改动应能映射到 acceptance criteria。

- 测试失败必须先读取错误信息，而不是盲目重复 run_tests。

- 测试通过并不自动意味着完成，还需 Final Verifier。

- 不允许要求或使用 Runtime 未注册的工具。

# 11. Tool System 设计

## 11.1 Tool 抽象

```python
class Tool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]

    @abstractmethod
    async def execute(
        self,
        args: BaseModel,
        ctx: ToolContext,
    ) -> ToolResult:
        ...
```

## 11.2 V1 Tool 清单

| **Tool**         | **输入**                   | **输出**                        | **底层实现**                  |
|------------------|----------------------------|---------------------------------|-------------------------------|
| repo.list_files  | path, depth                | 文件/目录列表                   | pathlib                       |
| repo.search_code | query, path, glob          | 匹配文件与行                    | ripgrep                       |
| repo.read_file   | path, start_line, end_line | 带行号文本                      | pathlib                       |
| code.apply_patch | unified diff               | 修改结果/失败原因               | git apply --check + git apply |
| code.create_file | path, content              | 创建结果                        | pathlib，受 Sandbox 限制      |
| test.run         | target, args               | stdout/stderr/exit_code/summary | pytest 子进程                 |
| git.diff         | path?                      | unified diff                    | git diff                      |
| git.status       | 无                         | 修改文件状态                    | git status --porcelain        |

## 11.3 为什么不开放通用 Shell

V1 不提供 shell(command) 是有意设计。Agent 的能力由明确 Tool 决定，Runtime 可以对每个工具做参数校验、路径约束、超时、日志和权限策略。如果未来确实需要 shell，应在容器级 Sandbox 中以 allowlist / command policy 方式实现，而不是直接把宿主 shell 暴露给模型。

## 11.4 Tool Description 规范

> **规范：**Tool description 不只是文档，也是模型选择工具的 Prompt。每个工具必须写清“什么时候用、什么时候不要用、输入限制、失败后如何处理”。

```yaml
name: repo.read_file
purpose: Read a UTF-8 source file from the active workspace.
use_when:
  - you need exact implementation details before editing
  - search results identify a relevant file
avoid_when:
  - you only need to locate symbols; use repo.search_code first
constraints:
  - path must be inside workspace
  - forbidden files are denied by runtime
```

# 12. Workspace Sandbox 与安全边界

## 12.1 Workspace 生命周期

```text
Base Repository (read-only baseline)
           │
           ▼
Create Run Workspace
workspaces/<run_id>/repo
           │
           ▼
Agent reads / edits / tests only here
           │
           ▼
Collect diff + result
           │
           ├─ Accept manually (future)
           └─ Delete / archive workspace
```

## 12.2 安全规则

- 所有 Tool 路径必须 resolve 后仍位于 workspace root 下。

- 默认拒绝 .env、.git/config、SSH key、系统目录和 workspace 外路径。

- 禁止通过 ../、symlink 等路径逃逸；创建 Workspace 后建议检查并限制 symlink。

- 网络访问默认关闭，保证 Eval 的可重复性。

- 测试子进程设置 timeout；输出截断并保存完整日志到 Run Artifact。

- Agent 不拥有自动 commit/push/merge 权限。

## 12.3 运行产物

```text
runs/<run_id>/
├── state.json
├── trace.jsonl
├── result.json
├── final.diff
├── test-output.log
└── workspace-metadata.json
```

# 13. Context Engineering 与 Prompt 设计

## 13.1 Context 构成

```text
System Instructions
+ Runtime / Security Policy Summary
+ DevelopmentTask
+ Current Phase
+ Current Plan
+ Relevant Repository Instructions
+ Relevant File Excerpts
+ Recent Observations
+ Current Test Failure / Verifier Feedback
```

## 13.2 不应该进入 Context 的内容

- 整个 Repository 的全部源码。

- 所有历史 Tool 输出的无限累积。

- 重复的大段 pytest 输出。

- Runtime 内部敏感配置、API Key、宿主环境信息。

- Hidden Tests。

## 13.3 Context 压缩策略

| **内容**                   | **策略**                                     |
|----------------------------|----------------------------------------------|
| Task / Acceptance Criteria | 始终完整保留                                 |
| Current Plan               | 始终保留最新版本                             |
| 当前相关源码               | 按需读取，控制行范围                         |
| 最近 Observation           | 完整保留最近 N 条                            |
| 更早 Observation           | 摘要为 Progress Summary                      |
| 测试输出                   | 保留失败测试、核心 stack trace；完整日志落盘 |
| Git Diff                   | 仅在验证/总结阶段按需加入                    |

## 13.4 Prompt 分层

```text
SYSTEM
  角色、目标、基本研发原则

POLICY
  工具边界、安全要求、完成规则

REPOSITORY INSTRUCTIONS
  ShopFlow 架构规范、测试约定、禁止规则

TASK
  Issue + acceptance criteria + constraints

STATE
  phase + plan + observations + relevant context
```

# 14. Verification 与停止条件

## 14.1 核心原则

> **硬规则：**LLM 可以“请求完成”，但 Runtime 才能“确认完成”。完成状态必须由 Deterministic Verifier 驱动。

## 14.2 V1 Verifier 检查

| **检查项**                   | **失败行为**                                     |
|------------------------------|--------------------------------------------------|
| Visible Tests                | 返回失败信息给 Agent；允许 repair loop           |
| Hidden Tests（Eval 模式）    | 评测判失败；正常 run 可不反馈具体 hidden 内容    |
| git diff 非空                | 无修改则不允许 Feature/Bug 任务完成              |
| Forbidden Files              | 发现则直接 Policy Failure                        |
| 修改文件数量                 | 超过阈值则失败或需人工批准                       |
| Ruff（可选 V1.1）            | 失败回灌或标记质量问题                           |
| Acceptance Criteria Coverage | V1 可由规则 + Agent Summary 辅助，后续引入 Judge |

## 14.3 完成状态判定

```python
completed = (
    agent_requested_finish
    and visible_tests_passed
    and no_policy_violation
    and diff_is_valid
    and required_verifications_passed
)
```

## 14.4 Final Report

```text
Task: DEV-001
Status: SUCCESS
Changed Files:
  - app/api/orders.py
  - app/repositories/order_repository.py
  - tests/api/test_orders.py
Tests: 47 passed
Verification: PASSED
Risk: Low
Summary: Added optional order-status filtering while preserving current behavior.
Suggested Commit: feat(order): support filtering orders by status
```

# 15. Trace / Observability

## 15.1 Trace Event Schema

```json
{
  "run_id": "run_...",
  "step": 7,
  "phase": "implementing",
  "event": "tool_call",
  "tool": "code.apply_patch",
  "arguments_summary": "patch app/api/orders.py",
  "timestamp": "..."
}
```

## 15.2 建议事件类型

- run_started / run_completed / run_failed

- agent_decision

- plan_created / plan_updated

- tool_call / tool_result / tool_error

- state_transition

- verifier_started / verifier_result

- guardrail_triggered

- context_compacted

## 15.3 V1 可观测指标

| **指标**              | **说明**                             |
|-----------------------|--------------------------------------|
| total_steps           | Agent 总决策步数                     |
| tool_calls            | Tool 调用数量                        |
| tool_failure_rate     | Tool 失败占比                        |
| test_retries          | 测试修复轮数                         |
| modified_files        | 修改文件数                           |
| duration_ms           | 总耗时                               |
| input/output tokens   | 模型 Token 消耗（若 SDK 提供）       |
| finish_rejected_count | Agent 请求完成但 Verifier 拒绝的次数 |

# 16. Eval 与 Issue Dataset

## 16.1 Eval 目标

Eval 的目标不是评判“回答看起来是否聪明”，而是验证 Agent 是否真正解决了研发任务、是否违反约束、是否过度修改、是否需要大量重试，以及不同 Runtime/Prompt/Tool 设计之间的真实差异。

## 16.2 Eval 执行流程

```text
Load Issue
   │
   ▼
Reset Base Repository
   │
   ▼
Create Clean Workspace
   │
   ▼
Run DevPilot
   │
   ▼
Run Visible Tests
   │
   ▼
Run Hidden Tests
   │
   ▼
Policy / Diff Checks
   │
   ▼
Collect Metrics
   │
   ▼
EvalResult.json
```

## 16.3 主要指标

| **Metric**             | **定义**                              |
|------------------------|---------------------------------------|
| Task Success Rate      | Hidden Tests + Policy + Diff 最终通过 |
| Visible Test Pass Rate | 公开测试通过率                        |
| Hidden Test Pass Rate  | 未暴露评测测试通过率                  |
| Regression Rate        | 原有测试被破坏的比例                  |
| Avg Steps              | 单任务平均 Agent Step                 |
| Avg Test Retries       | 平均修复轮次                          |
| Tool Failure Rate      | Tool 调用失败占比                     |
| Change Scope           | 修改文件/行数，衡量过度修改           |
| Token Cost             | 单 Issue Token 消耗                   |
| Runtime Duration       | 单 Issue 耗时                         |

## 16.4 Hidden Tests 原则

- Agent 不可读取 hidden_tests 目录。

- Hidden Tests 不能把具体失败内容完整回灌给 Agent，否则会泄露评测目标。

- Visible Tests 覆盖基本行为；Hidden Tests 覆盖边界输入、泛化能力、回归与约束。

- Eval Runner 在 Agent Run 完成后独立执行 Hidden Tests。

# 17. CLI 与运行流程

## 17.1 推荐 CLI

```bash
devpilot run evals/issues/DEV-001.yaml

devpilot inspect <run-id>
devpilot diff <run-id>

devpilot eval DEV-001
devpilot eval --all
```

## 17.2 run 命令流程

4.  解析 Task。

5.  创建 run_id 与 Workspace。

6.  从 baseline repo 复制/clone 干净代码。

7.  启动 CustomAgentRunner。

8.  持续输出 Rich CLI 的阶段、Tool、Test 状态。

9.  完成后打印 Summary，并把详细产物保存到 runs/\<run_id\>。

## 17.3 CLI 输出建议

```text
[DEV-001] understanding  -> parsed 4 acceptance criteria
[DEV-001] exploring      -> repo.search_code("orders")
[DEV-001] exploring      -> read app/api/orders.py
[DEV-001] planning       -> 5 steps created
[DEV-001] implementing   -> patch applied: app/api/orders.py
[DEV-001] verifying      -> pytest: 1 failed, 12 passed
[DEV-001] implementing   -> repair validation behavior
[DEV-001] verifying      -> pytest: 13 passed
[DEV-001] completed      -> verifier passed
```

# 18. 项目目录结构

## 18.1 DevPilot

```text
devpilot/
├── devpilot/
│   ├── domain/
│   │   ├── task.py
│   │   ├── state.py
│   │   ├── plan.py
│   │   └── result.py
│   ├── agents/
│   │   └── developer.py
│   ├── runtime/
│   │   ├── base.py
│   │   └── custom/
│   │       ├── runner.py
│   │       ├── loop_guard.py
│   │       ├── context.py
│   │       └── state_manager.py
│   ├── tools/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── repo/{list_files,search_code,read_file}.py
│   │   ├── code/{apply_patch,create_file}.py
│   │   ├── test/run_tests.py
│   │   └── git/{diff,status}.py
│   ├── workspace/sandbox.py
│   ├── verification/verifier.py
│   ├── llm/{base,openai}.py
│   ├── tracing/{events,writer}.py
│   └── cli.py
├── evals/
│   ├── runner.py
│   ├── metrics.py
│   ├── issues/
│   └── hidden_tests/
├── tests/
├── pyproject.toml
└── README.md
```

## 18.2 推荐基础依赖

```text
DevPilot:
  Python 3.12+
  uv
  openai
  pydantic
  pydantic-settings
  typer
  rich
  pytest / pytest-asyncio
  ruff
  ripgrep (system binary)
  git (system binary)

ShopFlow:
  FastAPI
  SQLAlchemy 2.x
  SQLite
  Pydantic
  pytest
  httpx
```

# 19. 开发阶段与任务拆解

## 19.1 Milestone 0 - Repository Bootstrap

| **任务**                                   | **输出**                |
|--------------------------------------------|-------------------------|
| 创建 devpilot 与 shopflow 两个独立项目     | 可分别 uv sync / pytest |
| 配置 Ruff / pytest / 基础 CI（可本地先做） | 统一质量基线            |
| 实现 DEV-001 baseline 与测试               | 第一个 Eval Task        |

## 19.2 Milestone 1 - Mock Backend

- 实现 Customer/Product/Order/OrderItem/Coupon 模型。

- 实现基础 API、Service、Repository、SQLite seed。

- 完成测试基线，确保 baseline 全绿。

- 准备 DEV-001 ~ DEV-005 对应分支/fixture 或可重置 baseline。

## 19.3 Milestone 2 - Tool Layer

- 实现 Tool base / ToolResult / ToolContext / Registry。

- 实现 repo.list_files / search_code / read_file。

- 实现 code.apply_patch，必须先 git apply --check。

- 实现 test.run、git.diff、git.status。

- 为每个 Tool 写安全、失败、路径越界单测。

## 19.4 Milestone 3 - Minimal Runtime

- 实现 DevPilotState、Observation、AgentDecision。

- 实现 LLMClient 抽象。

- 实现 DeveloperAgent.decide(context)。

- 实现 AgentRunner 和 max_steps。

- DEV-001 能完成“搜索 → 读文件 → patch → test → diff”。

## 19.5 Milestone 4 - Self-correction

- 将 test failure 作为 Observation 回灌。

- 支持 repair loop 与 max_test_retries。

- 加入重复 Tool Call 检测。

- Agent 请求 finish 后走 Final Verifier。

## 19.6 Milestone 5 - Planning & Context

- 加入 ImplementationPlan、PlanStep。

- ContextBuilder 按 phase 选择信息。

- 旧 Observation 压缩为摘要。

- DEV-001 ~ DEV-005 运行稳定。

## 19.7 Milestone 6 - Eval Harness

- 实现 issue loader / workspace reset。

- 实现 hidden tests 隔离。

- 输出 EvalResult JSON。

- 批量运行并生成版本对比表。

## 19.8 建议开发顺序

```text
ShopFlow baseline
    ↓
DEV-001 visible tests
    ↓
Repo Tools
    ↓
Patch Tool
    ↓
Test + Git Tools
    ↓
Minimal Agent Loop
    ↓
DEV-001 end-to-end
    ↓
Self-correction
    ↓
Verifier
    ↓
DEV-002 ~ DEV-005
    ↓
Eval Runner + Hidden Tests
```

# 20. 测试策略

## 20.1 DevPilot Unit Tests

| **模块**          | **关键测试**                                    |
|-------------------|-------------------------------------------------|
| Tool Registry     | 重复注册、未知 Tool、Schema 错误                |
| Path Guard        | ../、绝对路径、symlink、forbidden path          |
| Read/Search Tools | 空结果、Unicode、大文件截断                     |
| Patch Tool        | 合法 patch、context mismatch、越界文件、空 diff |
| Test Tool         | pass/fail/timeout/输出截断                      |
| Loop Guard        | max steps、重复动作、retry budget               |
| State Manager     | phase transition、Observation append、序列化    |
| Verifier          | tests fail、policy fail、empty diff、success    |

## 20.2 Integration Tests

- 使用临时 Git Repo 测试 Tool + Sandbox 联动。

- 使用 FakeLLMClient 固定输出 Tool Call，测试 Runtime 的 determinism。

- 模拟 patch fail → reread → patch success。

- 模拟 tests fail → repair → tests pass → verifier complete。

## 20.3 Agent Eval 与普通 Test 的区别

单元测试保证基础设施逻辑正确；Agent Eval 衡量模型驱动行为的成功率和稳定性。两者不能互相替代。Runtime/Tool 必须有 deterministic tests，Agent 行为必须有 repeated eval runs。

# 21. 框架升级与迁移策略

## 21.1 为什么 V1 先自研 Runtime

V1 需要亲自暴露 Agent Loop、Tool Dispatch、State、Context、Stop Condition、Verifier 等关键问题。这样后续引入框架时可以理解框架到底解决了什么，而不是只会调用 create_agent()/graph.invoke()。

## 21.2 迁移时哪些模块保留

| **模块**                          | **迁移影响**               |
|-----------------------------------|----------------------------|
| DevelopmentTask / Domain Models   | 极小                       |
| Repo/Code/Test/Git Tools 业务实现 | 小；增加 Framework Adapter |
| Sandbox                           | 基本不变                   |
| Verifier                          | 基本不变                   |
| Eval / Issue Dataset              | 基本不变                   |
| Prompt / Instructions             | 小到中                     |
| Agent Loop                        | 大；由框架替代             |
| State Progression                 | 中到大；映射到框架 State   |
| Context / Messages                | 中；适配框架消息模型       |
| Tracing                           | 中；可桥接框架 tracing     |

## 21.3 推荐 Runtime 目录演进

```text
runtime/
├── base.py
├── custom/
│   └── runner.py
├── langgraph/          # future
│   ├── adapter.py
│   └── graph.py
└── openai_agents/      # future
    ├── adapter.py
    └── runner.py
```

## 21.4 什么时候迁移 LangGraph 类框架

- while-loop 被大量 phase if/else 淹没。

- State Persistence / Resume 成为核心需求。

- 需要 Human Approval / Interrupt。

- Planning / Replanning 分支复杂。

- 工作流包含多个长时间等待事件。

- Multi-Agent 或复杂 Supervisor Workflow 出现。

## 21.5 推荐迁移方式

不要删除 Custom Runtime。增加第二个 Runtime Adapter，并让同一套 Issue Dataset、Tools、Verifier 在 custom 与 framework runtime 下运行。CLI 可支持 --runtime custom/langgraph，从而用真实指标比较 Success Rate、Steps、Tokens 和可靠性。

# 22. 风险、限制与后续路线图

## 22.1 主要风险

| **风险**     | **表现**                    | **缓解方案**                                    |
|--------------|-----------------------------|-------------------------------------------------|
| 模型过度修改 | 改动无关文件/重构过大       | max_modified_files、Prompt 最小修改、Diff Check |
| 无限循环     | 重复读文件/重复测试         | max_steps、重复动作检测、retry budget           |
| 测试投机     | 针对 visible test hard-code | Hidden Tests                                    |
| 上下文膨胀   | Token 快速增加              | 按需读取、Observation Summary、输出截断         |
| Patch 不稳定 | 上下文不匹配                | git apply --check，失败后 reread                |
| 安全越界     | 修改 workspace 外文件       | Path Guard、No Shell、Sandbox                   |
| 错误完成     | 模型说完成但实际失败        | Deterministic Verifier                          |
| 评测波动     | 相同任务成功率不稳定        | 多次运行、固定模型配置、统计分布                |

## 22.2 路线图

```text
V1    Issue → Code → Test → Repair → Verify
V1.1  Context compaction + Better planning
V1.2  Eval dashboard + regression benchmark
V2    GitHub Issue → Branch → PR + Human approval
V3    Project knowledge / RAG / Engineering memory
V4    Review Agent
V5    Framework Runtime + durable state
V6    Multi-Agent R&D Supervisor
V7    Logs / Metrics / Incident / SRE Agent
```

# 附录 A. V1 Issue Dataset

| **Issue** | **类型**    | **目标**                        | **主要能力**                                 | **难度** |
|-----------|-------------|---------------------------------|----------------------------------------------|----------|
| DEV-001   | Feature     | 订单列表增加 status filter      | Repo Explore + Patch + API Test              | ★        |
| DEV-002   | Bug         | 禁止 shipped/completed 订单取消 | 状态规则 + Regression Test                   | ★        |
| DEV-003   | Bug         | 订单分页边界修复                | API 参数 + Repository + Edge Cases           | ★★       |
| DEV-004   | Bug         | percentage coupon 计算错误      | Service 定位 + 业务计算 + Unit Test          | ★★       |
| DEV-005   | Performance | 订单详情 N+1 Query              | 跨 Repository 分析 + Batch Query + Perf Test | ★★★      |
| DEV-006   | Feature     | Email 规范化                    | Validation + Compatibility                   | ★★       |
| DEV-007   | Bug         | 防止重复支付                    | Idempotency / 状态一致性                     | ★★★      |
| DEV-008   | Feature     | Order audit fields              | Schema + Persistence + API Compatibility     | ★★★      |

## A.1 DEV-002 示例

```text
Title: Prevent invalid order cancellation
Expected transitions:
  pending   -> cancelled  allowed
  paid      -> cancelled  allowed
  shipped   -> cancelled  rejected
  completed -> cancelled  rejected
Acceptance:
  - invalid transitions return HTTP 409
  - existing valid transitions keep working
  - regression tests required
```

## A.2 DEV-005 示例

```text
Title: Optimize order detail for large orders
Problem:
  GET /orders/{id} takes > 2s for an order containing 1000 items.
Acceptance:
  - no API response schema changes
  - replace per-item product lookup with a batch strategy
  - performance test threshold < 500ms in test fixture
  - existing behavior remains correct
```

# 附录 B. Tool 接口草案

## B.1 repo.search_code

```text
Input:
  query: str
  path: str = "."
  glob: str | None = None
  max_results: int = 50

Output:
  matches: [
    {path, line, text}
  ]
  truncated: bool
```

## B.2 repo.read_file

```text
Input:
  path: str
  start_line: int | None
  end_line: int | None

Output:
  path: str
  start_line: int
  end_line: int
  content: str
  truncated: bool
```

## B.3 code.apply_patch

```text
Input:
  patch: str   # unified diff only

Runtime flow:
  1. parse target paths
  2. path policy check
  3. git apply --check
  4. git apply
  5. git diff --stat

Output:
  success: bool
  modified_files: list[str]
  error: str | None
```

## B.4 test.run

```text
Input:
  target: str | None
  extra_args: list[str] = []

Policy:
  - executes pytest only
  - workspace cwd only
  - timeout enforced

Output:
  exit_code: int
  passed: int | None
  failed: int | None
  duration_ms: int
  summary: str
  log_file: str
```

# 附录 C. 配置项建议

```dotenv
# .env / settings (example; secrets are never exposed to Agent context)
DEVPILOT_MODEL=...
DEVPILOT_MAX_STEPS=30
DEVPILOT_MAX_TEST_RETRIES=3
DEVPILOT_MAX_MODIFIED_FILES=10
DEVPILOT_TEST_TIMEOUT_SECONDS=120
DEVPILOT_NETWORK_ACCESS=false
DEVPILOT_WORKSPACE_ROOT=./workspaces
DEVPILOT_RUNS_ROOT=./runs
DEVPILOT_BASE_REPO=../shopflow-order-service
```

## C.1 LLM 参数原则

- 模型调用统一走 LLMClient，不在业务代码里散落 provider SDK 调用。

- 记录模型名、request_id（若有）、tokens、latency，便于 Eval 对比。

- AgentDecision 使用结构化 Schema，避免解析自由文本控制动作。

- Prompt 中不暴露 API Key、真实环境变量或 hidden test 路径。

# 附录 D. Definition of Done

## D.1 DevPilot V1 发布条件

| **检查项**        | **完成标准**                                 |
|-------------------|----------------------------------------------|
| ShopFlow Baseline | 完整测试通过，可快速重置                     |
| Tools             | 8 个核心 Tool 全部有单测与路径保护           |
| Sandbox           | workspace 外读写测试被拒绝                   |
| Runtime           | max steps/retry/finish verifier 有自动化测试 |
| DEV-001           | 可端到端稳定完成                             |
| DEV-002 ~ DEV-005 | 至少 3/4 可在目标模型配置下成功              |
| Trace             | 每个 Run 可回放主要动作                      |
| Hidden Tests      | Agent 无法读取，Eval Runner 可执行           |
| Documentation     | README 包含运行、测试、Eval、架构和限制      |
| Framework Ready   | 业务 Tool/Verifier/Domain 不依赖具体框架     |

## D.2 第一阶段开工清单

10. 创建 devpilot 与 shopflow-order-service 两个仓库/目录。

11. 先完成 ShopFlow baseline，不写 Agent。

12. 实现 DEV-001 的 Issue、Visible Tests 与 Hidden Tests。

13. 实现 Repo/Search/Read、Patch、Test、Git 五类最小 Tool。

14. 使用 FakeLLMClient 把 Runtime Loop 测通，再接真实 LLM。

15. 让 DEV-001 完成第一次真实端到端自动修复。

16. 加入 Final Verifier、Trace 与 EvalResult。

17. 扩展 DEV-002 ~ DEV-005，并开始比较成功率而不是只看单次 Demo。

> **建议的第一条主线：**先把 DEV-001 跑通，再加能力。不要同时实现 RAG、Multi-Agent、Web UI、GitHub App、LangGraph。V1 的价值是把“决策 → 工具 → 观察 → 状态 → 验证”这一条链真正做扎实。

— DevPilot V1 Development Design —
