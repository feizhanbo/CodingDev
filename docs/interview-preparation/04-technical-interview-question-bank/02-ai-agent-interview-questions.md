# AI 应用开发专项

A01–A09 是专项主问题；架构权衡见 D，故障场景见 S，六层训练见 T。题目中的源码代号在 README 统一解析。

## A01｜P0·中级｜LangGraph 具体做什么？State、Node、Edge 与领域 phase 有何关系？

**考察**：编排原理。**简答**：图保存并推进执行状态；节点调用业务步骤，条件边依据 decision/result/failure 选择后继。领域 phase 描述业务进展，不是当前节点名称。

**展开**：GraphState 包含 domain、decision、accounting、recovery 等序列化投影；运行时客户端和锁留在依赖对象中。action→execute_tool→observe，finish→verify，拒绝后回 guard。当前图串行；async 节点不自动变成多 Agent 并行系统。DeveloperAgent 选择下一动作，图和守卫约束执行。

**原理/追问**：状态机、依赖分离；为何不用一个节点包住旧 run？这样没有暴露内部恢复边界。继续 D01/T1。

**证据**：R，test_graph_topology。**评价**：合格能画真实路径；深入区分 phase/节点/模型；把 LangGraph 说成模型或自动多 Agent 是盲区。

## A02｜P0·中级｜ToolRegistry 如何把模型动作变成可控执行？

**考察**：边界与工具协议。**简答**：注册具名工具和别名，查找工具后按专属 Pydantic 输入模型校验，再携带 deadline、路径和输出预算执行，返回 ToolResult。

**展开**：外层 AgentDecision 只保证 action 形状，arguments 仍是 dict；工具参数需要第二次校验。未知工具/参数错误成为失败观察，普通异常也可转 ToolResult；配额异常明确重抛，取消不被普通 Exception 吞掉。路径和冻结测试保护由具体工具继续执行。

**原理/追问**：分层验证与白名单派发；合法参数就安全了吗？还需路径、操作对象和验收约束。继续 A03/T5。

**证据**：F，test_registry。**评价**：深入会纠正源码注释 never raises 的过宽说法；只说“调用工具 API”不够。

## A03｜P0·中级｜Observation 为什么必要，工具失败之后模型看到什么？

**考察**：反馈闭环。**简答**：Observation 是执行事实而非模型意图，保存成功与否、结构化 data 和耗时；ContextBuilder 将最新事实带入下一轮。

**展开**：observe_step 补充失败测试结构后交 StateManager，记录 TestRun 与修改文件；test 和 verification 使用不同 repair_sources。后续 test.run 成功不应清除独立验收失败；最近成功测试会取代旧的当前测试失败提示。否则模型可能重复修已经解决的问题。

**原理/追问**：事实状态与提示投影；观察太多怎么办？A07。无限 plan_update 怎么办？LoopGuard 软反馈和硬停止，并受全局预算约束。

**证据**：C、R，test_context_feedback、test_repair_loop。**评价**：合格能连到下一轮；深入说明失败来源和最新事实；“自动修复必成功”不成立。

## A04｜P0·中级｜finish 为什么不代表完成？冻结了什么，如何独立验证？

**考察**：可信验收。**简答**：finish 是模型请求；Verifier 对冻结清单与候选副本执行独立检查和测试，避免模型通过改测试制造成功。

**展开**：capture_snapshot 保存纳入清单的全部文件，protected 子集禁止修改。物化前核验基线与受保护文件，按实际文件清单导出包含新增/删除的 diff；冻结 visible 和 added tests 分开运行。缺快照、空 diff、失败或跳过等不能简单算通过。

**原理/追问**：独立证据与信任域；是否绝对防作弊？没有 OS 隔离，同机恶意 Python 仍超出边界。继续 T2。

**证据**：V，test_evidence。**评价**：深入能说清 candidate 与测试 harness；认为“换个目录就安全”需要纠正。

## A05｜P0·中级｜Smoke、Capability、hidden tests 和 coverage 有什么区别？

**考察**：评测口径。**简答**：Fake smoke 只验证执行闭环，hidden 为 NOT_EVALUATED，不纳入能力成功；capability 需要真实任务及可信验收。coverage 描述条件绑定，不能把测试通过率当需求覆盖率。

**展开**：EvalRunner 区分 PASS/FAIL/ERROR/NOT_EVALUATED，缺少证据不应计成功。coverage_for 主要用“新增测试”等关键词映射 required_new_tests，多数条件 uncovered；verify.success 不要求每个条件 verified。确定性八任务验收也不是模型解题率。

**原理/追问**：指标分母、选择偏差；如何改进覆盖？扩展方案为显式 criterion→check 映射并保留未测项，不让模型自报覆盖。继续 T2 第5/6层。

**证据**：E、V，test_eval_truthfulness。**评价**：深入区分基础设施与能力；把未知算零分或成功都可能歪曲结果，应保留独立状态。

## A06｜P0·高级｜Checkpoint 与 OperationJournal 分别解决什么问题？

**考察**：恢复语义。**简答**：前者恢复控制流位置和状态，后者判断工具副作用是否已有可信结果。它们没有跨文件/模型/SQLite 的共同事务。

**展开**：begin 写 prepared，complete 保存后置摘要和输出。恢复参数一致、completed、after 与当前状态匹配且结果摘要有效才复用；prepared 工具拒绝盲重放。模型请求另有对账逻辑：未知尝试仍计数，可能继续有限重试。

**原理/追问**：重放、幂等与原子性范围；为何不是 exactly-once？存在副作用后回执前窗口。继续 T3。

**证据**：J，test_operation_journal、test_model_reconciliation。**评价**：必须指出不确定窗口；只背 prepared/completed 而说是 2PC 不合格。

## A07｜P1·中级｜上下文如何压缩，哪些信息不能丢？

**考察**：上下文工程。**简答**：系统、任务、计划和阶段信息组织成消息；旧观察做规则摘要，近期保留细节；硬预算裁剪可删除观察，保护当前修复和守卫反馈。

**展开**：在状态副本上裁剪，不删除真实历史。固定内容仍超过字符预算就 ContextBudgetExceeded；prepare_messages 加协议提示后再检查。字符不是 token，摘要也不无损，必要时需重新读取文件。这里没有向量检索或跨 run 记忆。

**原理/追问**：有损压缩与检索不同；为什么不直接加 RAG？先确认瓶颈是相关性检索还是当前消息预算，RAG 不能替代失败事实保留。

**证据**：C、M，test_context_compression。**评价**：合格知道压缩策略；深入说明硬失败和保留信息；声称精确 token 控制不准确。

## A08｜P0·中级｜JSON object 和 Pydantic 是否保证决策正确？

**考察**：结构化输出边界。**简答**：不能。JSON 模式请求格式，AgentDecision 校验 action/plan_update/finish 恰有一支，Registry 再验证工具参数，最后还要验证业务结果。

**展开**：LangChain 与 OpenAI 适配复用协议和解析器，Fake 返回同一领域响应。工具描述进入提示，不等于原生 function calling。JSON 字段合法但可以请求错误文件或错误算法；parser 的兜底括号扫描也不理解字符串内括号。

**原理/追问**：语法、类型、权限、业务语义四层不同。改用原生工具调用是否省掉 Verifier？不省。继续 S02。

**证据**：M、F、V，domain/test_models、test_langchain_transport。**评价**：深入指出额外字段/类型并非统一 strict forbid；“结构化输出杜绝幻觉”是错误。

## A09｜P1·高级｜怎样观察运行过程，怎样证明你保存的是事实？

**考察**：可观测性与证据。**简答**：用 run、step、事件身份关联 Trace、请求记录、测试报告和最终 diff；日志用于诊断，最终验收依赖独立产物，不只依赖日志文本。

**展开**：Graph 有 trace_sequence 和事件身份治理，恢复应避免把重放观察重复统计；请求账本保留 unknown usage。持久化失败需要影响交付状态，不能吞掉异常后仍展示成功。当前是本地观测，不是线上集中监控或 Langfuse 集成。

**原理/追问**：事件身份与指标去重；日志泄密和无限增长怎么办？脱敏、输出限制和产物配额，但不宣称覆盖未知秘密。继续 S04。

**证据**：L、J、B，test_identity、test_terminal_publication。**评价**：深入区分日志、账本和验收证据；报出不存在的生产告警经验扣分。
