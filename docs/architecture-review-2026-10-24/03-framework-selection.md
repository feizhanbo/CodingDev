# Agent 框架选型与路线比较

评估日期：2026-10-24。项目证据见 [架构审计](G:/program/CodingDev/docs/architecture-review-2026-10-24/01-current-architecture.md)，需求缺口见 [问题清单](G:/program/CodingDev/docs/architecture-review-2026-10-24/02-problems-and-necessity.md)。本报告查询了官方文档与仓库；没有安装候选框架、运行框架 PoC 或进行收费模型比较。因此“适配度”是基于调用边界的工程判断，不是性能实测排名。

## 1. 选型基准：先明确需要替代什么

现有 `DeveloperAgent.decide(context) -> AgentDecision` 已可用，`ToolRegistry.execute(action, ctx) -> ToolResult` 和独立验收比通用 agent demo 更严格。优先需要替代的是 CustomAgentRunner 的控制流、持久人工中断和可检查的执行状态，而非重新购买一个模型/工具循环。

硬性门槛：

1. 可以让现有确定性服务决定工具权限、资源预算与最终验收，框架不能自行宣布成功。
2. 保留 async 接口、Pydantic 领域模型与现有 OpenAI-compatible/FakeLLM 客户端。
3. 本地离线测试可执行，不依赖托管平台、在线 trace 或额外模型调用。
4. checkpoint 的“图恢复”必须与工作区副作用一致性分开；不安全重放必须能阻断。
5. 可在相同 Runtime 契约下对比，不要求 EvalRunner 理解框架内部消息格式。

## 2. 官方能力核查与适配判断

### LangGraph：与本次编排边界最匹配

官方 Graph API 以 state、节点函数和条件边表达循环；节点可直接运行普通 Python 服务，因此可以保留 DeveloperAgent/ToolRegistry/TaskVerifier，不强制改为预制 Agent 或原生工具调用消息。[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)

checkpointer 持久化 thread 的图状态；生产持久化不能使用 InMemorySaver。本地可评估 SQLite，未来并发服务再评估 PostgreSQL，二者都需实际存储、备份和保留策略。[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

官方还提供节点重试和 timeout 配置，但它们只能作为执行外壳；本项目应由一个 BudgetLedger 控制总尝试数，且阻塞进程必须由 ProcessExecutor 清理。不能同时启用 SDK、节点和业务三层独立重试。[Graph API 使用指南](https://docs.langchain.com/oss/python/langgraph/use-graph-api)

`interrupt`/`Command` 可承载待人工处理状态；恢复时包含 interrupt 的节点会重新执行，所以前置副作用应幂等或拆分。本项目必须在补丁执行前独立审批节点，并用操作日志对账，不能把一个完整 `CustomAgentRunner.run()` 包成单个节点就声称完成迁移。[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)

**解决的真实问题**：P06/P07 的分支可视性与集中编排、P08 的持久人工暂停及图进度；对 P09 的收益以先抽取接口为前提。**新增成本**：图状态序列化、节点重放、super-step 与业务 step 的区别、数据库迁移/配额、异常投影。**不解决**：权限、测试独立性、自然语言验收覆盖与费用治理。

### PydanticAI / pydantic-graph：结构化模型层强候选，亦可做编排

PydanticAI 支持类型化输出、依赖注入和 UsageLimits；已有请求/Token 等限制机制，可减少本项目输出解析和模型适配代码。恢复时需带入此前 usage 才能约束跨运行总量，不能把默认新 run 预算当作当前恢复预算。[Agents / Usage Limits](https://pydantic.dev/docs/ai/core-concepts/agent/)

`pydantic-graph` 有 GraphBuilder、类型化 state/deps、节点/step 与分支，不应误写为只能单 Agent 简单对话。官方还提供 durable execution 引擎集成；其持久执行方案与所选后端有关，不能把普通消息历史序列化等同完整断点恢复。[Graphs](https://pydantic.dev/docs/ai/graph/graph/)、[Durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)

TestModel/FunctionModel 与测试期禁止真实模型请求机制便于离线验证；仍需适配本项目既有按序 AgentDecision 的 FakeLLM 和工具轨迹断言。[Unit testing](https://pydantic.dev/docs/ai/guides/testing/)

**项目适配**：若主要痛点变成多供应商、严格结构化输出和模型协议，优先级会上升。本轮若只替换 `llm/openai.py`，P06/P08 仍大部分存在；若同时采用 Agent 内循环 + graph/durable backend，则要治理两套重试与 checkpoint。可作为 LangGraph PoC 不达标时的类型化编排备选；不建议首轮同时引入 LangGraph 和 PydanticAI。

### AutoGen：可表达多 Agent，但不适合作为新的长期核心

AgentChat/Core 支持会话式单/多 Agent，save_state/load_state 提供状态保存接口；其持久化存储、外部工具副作用和恢复时机仍需宿主负责。不能把团队对话状态直接等同 DevPilotState、工作区文件与冻结证据的一致快照。[AutoGen 架构](https://microsoft.github.io/autogen/stable/)、[Managing State](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html)

本次检索时官方仓库 README 顶部明确声明项目已归档、不再由 Microsoft 提供维护，并建议迁移至 Microsoft Agent Framework；同页后部还残留 maintenance-mode 文案。以顶部明确生命周期声明为当前选型约束，不将它视为仍积极发展的默认新项目路线。正式落地前应复核该状态。[官方仓库](https://github.com/microsoft/autogen)

**项目适配**：现有开发任务是单写者循环，验收者是确定性验证器，不应为了“多 Agent”把它换成另一位会话 Agent。采用 AgentChat 意味着重映射消息/工具结果/停止条件，保留安全执行器仍不可省；新增长期维护风险超过本轮收益。

### CrewAI：Flows 有真正的状态与恢复能力，但职责模型更宽

Flows 提供事件/路由编排、Pydantic 或字典状态及 `@persist`，默认持久化可使用 SQLite；当前文档还单列 checkpointing，因此不能沿用“CrewAI 没有 checkpoint”的旧结论。状态 hydration/fork 与流程执行恢复的语义需要按相应接口分别验证。[Flows](https://docs.crewai.com/v1.15.30/en/concepts/flows)、[Checkpointing](https://docs.crewai.com/v1.15.30/en/concepts/checkpointing)

Flow 人工反馈也有专门接口，可以构造审批和路由；是否满足本项目进程退出后恢复、预算冻结及工具去重，仍需专用测试。[Human Feedback](https://docs.crewai.com/v1.15.30/en/learn/human-feedback-in-flows)

一个具体不匹配点是官方 checkpoint 文档将事件触发的自动写入定义为 best-effort：写入失败记录日志后继续；手动 checkpoint 才重新抛出错误。DevPilot 当前在派发外部操作前要求 checkpoint 成功，若采用 CrewAI，必须额外建立这一强制持久化边界，不能直接沿用默认行为。[Checkpointing 错误语义](https://docs.crewai.com/v1.15.30/en/concepts/checkpointing)

**项目适配**：只使用 Flow 包装既有服务是可行备选；如果进一步采用角色/Task/Crew 模式，则会重定义现有 DevelopmentTask、计划、完成和模型循环。当前尚无明确角色协作需求，这些抽象的迁移收益小。建议只有未来产品主要是角色分工流程时提高其优先级。

### 补充：Microsoft Agent Framework

因为 AutoGen 官方给出继任方向，补充评估该候选，而非把生命周期问题忽略。其官方概览列出 Agent、显式 workflows、model clients、session 和 middleware；具备复用 Python 服务的可能性。[官方概览](https://learn.microsoft.com/en-us/agent-framework/overview/)

本项目没有已确定的 Microsoft 平台依赖；现阶段再更换模型/session 抽象没有明显优势。作为后续跨平台/多 Agent 集成候选保留，不在本轮与 LangGraph 并行引入。文档能力不等于已在本机验证，尤其不能从概览推定所有持久化后端和 Windows 取消语义。

## 3. 九维比较与当前代码落点

表中“需自建”只表示本项目必要集成，不是断言框架完全没有相关 API。

| 维度/代码需求 | LangGraph | PydanticAI + graph | AutoGen | CrewAI Flows |
|---|---|---|---|---|
| 编排/条件分支：替代 runner._run 嵌套逻辑 | 显式图/条件边，直接包普通服务；最贴近 | 类型化图可行；Agent 层与 graph 分工需选定 | 对话/team 强，需映射独立验证分支 | Flow 路由可行；避免额外 Crew 内循环 |
| 状态/checkpoint：保留请求/repair/文件身份 | 图 checkpoint + 业务操作日志；state 可序列化 | state/graph + 所选持久后端；恢复对账仍自建 | agent/team state 保存不是文件事务 | persistence/checkpoint 需测试恢复粒度；文件对账自建 |
| 工具/输出/model：保留 AgentDecision 和 Registry | 节点内直接调用旧接口；最少协议变化 | 强类型输出和依赖自然；工具适配与消息迁移增加工作 | 工具/message 转换较多 | Flow 可直调；采用 Crew 时须适配工具与 Task 输出 |
| 自修复/重试/timeout | 显式 repair 边；保留统一预算与进程执行器 | 可用 typed retry/limits，但须避免嵌套重试 | termination/cancellation 需与原预算对齐 | Flow/Agent 限制与原预算需统一所有权 |
| 单/多 Agent | 当前串行图；未来独立子图；写仓库仍单写者 | typed agent/graph 可组合；同样需协调写权限 | 会话团队是主要契合点，当前需求弱 | 角色协作是契合点，当前需求弱 |
| 人工介入/生命周期 | interrupt 适合持久暂停，须拆副作用节点 | deferred tools/外部持久引擎可选，生命周期需接入 | 人工消息与保存/恢复接口需应用组合 | human_feedback + persistence 可选，需绑定预算/身份 |
| 可观测/测试/eval | 继续 JSONL/FakeLLM；节点事件映射，非强制托管观测 | 测试替身方便，原 Fake 需桥接；eval 保持外部 | 团队事件映射到统一契约，避免按会话停止判成功 | Flow 事件映射；保留外部隐藏测试，不能依赖 Crew 自评 |
| Python/Pydantic/SDK/asyncio | 原有 async 服务直接节点化，锁依赖验证 | Pydantic 贴近现有模型；OpenAI/Fake 接口有改造 | Python 异步可行，模型客户端与消息模型变化较多 | Python/Pydantic/异步可行，Flow 可轻用，Crew 较重 |
| 维护/成本/风险 | 中等；风险集中于持久化/重放，可局部试点 | 模型层低到中，整体持久化中到高 | 高；生命周期状态不利新核心 | Flow 中等，全面 Crew 高；需约束隐藏循环 |

安全隔离、原测试保护、Benchmark 公正性、请求成本都应作为四者共同的外部条件，不能写进某框架的“自动解决清单”。

## 4. 三条路线

| 路线 | 范围 | 优势 | 缺点与迁移风险 | 估算与适用条件 |
|---|---|---|---|---|
| A：优化 custom | 修 P01–P03、拆公共服务、清晰状态/评估契约，继续当前循环与保守恢复 | 依赖最少；行为差异可控；现有测试复用最大 | 将来人工暂停/复杂分支仍需自行扩展编排；保留自研维护责任 | 约 11–17 人日（计划 P0–P2）；短任务/单 Agent 足够时合理 |
| B：局部框架编排 | A 的共享服务 + LangGraphRunner；原客户端/工具/验收/评估保留 | 直接解决编排扩展；同一业务代码支持双 Runtime；可回退 | graph checkpoint 与文件副作用需设计；双轨只能短期；增加库/存储兼容责任 | 约 24–38 人日（P0–P5 全部）；本次推荐 |
| C：框架重组整个 Runtime | 同时迁移 Agent、消息、模型、工具包装、状态、恢复、评估接入 | 从框架范式出发可统一体验；未来高度框架化协作更顺畅 | 多个行为变量同时变化，预算/验收可能退化，Fake/历史产物大量适配；没有证据支持当前收益 | 约 45–70 人日，需重新估算；只有明确长期产品约束且 B 无法满足才采用 |

人日是熟悉 Python/asyncio 的单工程师实施加自测范围估算，含测试/评审修订；不含新 OS 隔离平台、产品审批 UI、真实模型收费评测、跨团队排期。不是项目现有性能或交付承诺。

## 5. 推荐决策与退出条件

**推荐 B：LangGraph 只负责显式编排与图持久状态，先完成 A 的公共服务和工程修复。** 关键理由是与“把现有确定性函数连成可恢复工作流”的目标一致，较少改变模型行为和工具协议。最终是否默认启用，由相同输入/预算/验证器下的离线契约、故障注入与开销对照决定。

不将 PydanticAI 同时引入首轮。后续若供应商适配/输出协议成为主要瓶颈，可在 `DecisionService` 后面单独替换并测试。AutoGen 的生命周期不利于新核心；CrewAI 的 Flow 能力应被认可，但当前角色式抽象没有必须采用的业务依据。

如果 P0–P2 已足够满足近期需求，可停留 A；如果 LangGraph 的恢复对账复杂度没有下降或同样任务开销明显恶化，回退 A，保留抽取的公共服务与测试。没有“必须框架化”的不可逆前提。

## 6. 版本与证据管理

本次引用在线官方文档的查询版本；CrewAI 页面重定向到 v1.15.30，其他文档可能继续变化。这些不是 DevPilot 已锁定的依赖版本。本轮不改 `pyproject.toml`/`uv.lock`。P3 实施时选择并锁定一组兼容版本，记录 Python、Pydantic、langgraph、checkpoint backend、langchain-core 等实际传递依赖，执行 Windows/Linux CI 与依赖审计。未验证的“最新版本最好”“框架显著节省 Token”等结论均不采用。

