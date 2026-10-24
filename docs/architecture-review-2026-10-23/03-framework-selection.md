# Agent 框架选型对比

核查日期：2026-10-23。以下框架能力来自官方资料；对 DevPilot 的适配判断和工作量为本次架构推断，未安装框架、未运行框架 PoC、未宣称提升真实模型成功率。网页会滚动更新，实施前应锁定版本、Python 3.12/Windows 依赖矩阵与 checkpoint 后端并通过本项目测试。

## 官方能力与项目映射

|维度|LangGraph|PydanticAI / pydantic-graph|AutoGen|CrewAI|
|---|---|---|---|---|
|条件分支/循环|图节点与条件边，适合拆 _run|类型化图及节点，适合显式状态工作流|Core 消息运行时、AgentChat 团队；改为消息协议工作较多|Flows 事件、router/listen 支持分支循环|
|状态/恢复|checkpointer 保存 thread 状态；持久后端必选|图状态与持久能力；更强耐久执行可接独立引擎|save_state/load_state 保存 Agent/Team 状态；不能等同外部动作 exactly-once|Flows 状态和 persistence/checkpoint 能力；需要验证业务副作用恢复契约|
|工具/结构输出|可把现有 decide/registry 直接包装为普通 async 节点|Pydantic 输出及工具/依赖建模与项目接近；改 LLM 层收益较直接|需包装模型客户端、消息及工具返回值|需包装 Task/Agent/tool；Flow 可只调用现有服务|
|重试/异常/超时|节点重试不替代总预算、进程树清理|输出校验重试与耐久引擎可能叠加现有重试|终止条件和取消 token 需映射现有预算|任务/流程重试需与现有 repair/预算分离|
|单/多 Agent|单图可起步，后续子图；不要求现在引入多 Agent|单 Agent 适配自然，图/组合扩展|团队协作优势明显，但当前需求是单开发者|角色/任务协作便利，但不是当前瓶颈|
|人工介入|interrupt + Command(resume)，需稳定 thread_id|deferred tools/工作流能力需结合选定持久方案|UserProxy/人类输入与状态保存结合|Flow 人工反馈机制，需配生命周期接口|
|观测/测试|保留 TraceWriter/FakeLLM，节点事件追加；无须云服务|测试模型/函数替身及观测能力；仍保留 FakeLLM 基线|事件/日志接桥接层；需重新对齐团队消息计数|事件监听桥接；保留本地验收与评估|
|Python/Pydantic/asyncio|async 节点可继续调用现有 SDK 和 Pydantic 对象|技术栈最相近，但改 Agent 契约影响提示及请求分布|async 兼容；增加消息/团队状态模型|Flow 可使用 Pydantic，需确认 async 和依赖树兼容|
|本项目成本/风险|中：图调度与 checkpoint 转换；重放副作用是核心风险|中：仅换模型层容易，但图+耐久方案会增加选择与集成面|高：团队抽象与现有单循环不匹配，另有维护方向变化|中高：部分 Flow 可行，全 Crew 重写会改变计划和工具策略|

LangGraph 的图状态、节点、条件边及重执行语义见 [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)，checkpointer 与存储的职责见 [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)，人工恢复需持久后端和 thread_id，见 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。DevPilot 应使用这些底层能力包装现有服务，不必同时迁移到另一套预制 Agent。

PydanticAI 不能被简化为“没有图或恢复”。官方提供 [Graphs](https://pydantic.dev/docs/ai/graph/graph/)、[Durable Execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)、[结构输出](https://pydantic.dev/docs/ai/core-concepts/output/) 和 [测试替身](https://pydantic.dev/docs/ai/guides/testing/)。其价值主要是 DeveloperAgent/OpenAIClient 的结构输出和依赖建模；当前优先瓶颈在 orchestration，因此暂不同时更换模型层。若后续主要痛点变为多 provider 输出兼容，可重新评估。

AutoGen 官方当前声明进入维护模式并建议新项目使用 Microsoft Agent Framework，见 [AutoGen 官方仓库](https://github.com/microsoft/autogen)。其 [AgentChat 状态管理](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html) 可以保存/加载 Agent 与 Team，但 DevPilot 的文件修改、测试执行和预算仍需另外实现一致性。故不建议新增 AutoGen 作为本项目战略依赖。补充候选 [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) 支持 Python/.NET 和多 Agent 工作流，当前没有跨语言或该生态约束，暂列观察项；本轮没有做其深度 PoC。

CrewAI 的 [Flows](https://docs.crewai.com/v1.15.28/en/concepts/flows) 支持结构化状态、条件与循环，不能因名称带 Crew 就否认其单流程能力。对本项目可包装现有工具和验证，但引入 Crew 角色/任务层会扩大对 prompt、plan 和模型轮次的改变。只有未来产品明确以角色分工作为核心时才优先重评。

## 三条路线

|路线|优势|缺点与成本估计|迁移风险|适用条件|
|---|---|---|---|---|
|A 保留 Custom Runtime|保留现有语义、依赖少，直接修复真实缺陷|约 8–13 人日完成基线/规则/接口治理；后续 HITL 与更强恢复需自己维护|低至中，仍需修状态回归|短任务、单 Agent、没有明确持久审批需求|
|B 框架负责部分编排（推荐）|共享工具、模型、验收和评估；替换循环调度、节点 checkpoint、interrupt|完整阶段约 28–45 人日；先小规模图试点，不要求马上切默认|中；重点是 checkpoint 与副作用一致性、预算计数|需要扩展恢复/人工介入且可渐进交付|
|C 框架核心全面重组|统一框架 Agent/消息/工具生态，长远抽象一致|约 45–70 人日以上；同时改模型、上下文、工具与结果映射，估算不含生产隔离平台|高，难区分模型行为变化与运行器回归；大量已成熟规则要重新证明|现有接口几乎不可复用，或明确必须围绕另一生态重建产品|

估算以一位熟悉项目的 Python 工程师为基准，不含需求评审等待、收费模型评估、生产容器/VM 平台建设。B 的分阶段拆解见实施计划；不是交付承诺。

## 推荐决策及反证条件

建议 B：LangGraph 仅接管显式执行图、条件边、持久节点状态和人工中断入口；保留 DeveloperAgent、LLMClient、ToolRegistry、Workspace、LoopGuard 业务规则、TaskVerifier、Benchmark 和 Trace 的契约。先执行 A 与 B 共用的工程治理阶段，再做图试点。

选择理由是能将 `CustomAgentRunner._run` 拆成普通 Python/async 节点，而不用同时改变模型输出、工具语义和测试策略；目前已存在 Protocol 与稳定 DTO，可用低耦合适配器承接。LangGraph 不会解决 F01–F05、资源与验收问题，PoC 不通过就停留 A。

出现以下任一条件应否决默认替换：需要维护两套预算/验收业务逻辑；必须放宽原测试保护才可运行；不能解释恢复后模型调用次数；无法阻止 uncertain patch 重放；稳定本地 checkpoint 后端在目标 Windows/Python 版本无法通过故障测试。没有实时付费 A/B 数据前，不承诺更高能力成功率或更低 token 消耗。
