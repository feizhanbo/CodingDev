# 第四阶段：项目面试题库与连续追问

基线：`41c4ea517e12384a87bb11cb8ed0995aa995ba4a`，日期2026-11-09。沿用前三阶段定位与修正，重新核对当前关键源码。只新增文档，不改业务代码。

## 导航与覆盖矩阵

| 内容 | 文档/题号 | 覆盖与学习层次 |
| --- | --- | --- |
| 项目全貌 | [整体理解](01-project-overview-questions.md) O01–O05 | 业务、入口、边界、历史证据、个人职责 |
| AI专项 | [Agent题库](02-ai-agent-interview-questions.md) A01–A09 | 编排、工具、反馈、验收、评测、恢复、上下文、协议、观测 |
| 后端专项 | [Python后端](03-python-backend-interview-questions.md) B01–B09 | 异步、资源、事务、条件更新、幂等、数据库、依赖抽象 |
| 技术权衡 | [架构题](04-architecture-and-design-questions.md) D01–D05 | 框架/兼容、持久化、规模、锁、协议 |
| 故障场景 | [排查题](05-scenario-and-troubleshooting-questions.md) S01–S08 | 崩溃、无效决策、未知费用、持久化、并发工作区、订单、多Worker |
| 六个核心案例 | [六层追问树](06-deep-follow-up-trees.md) T1–T6 | 每树六层；问题、目的、要点、参考回答、原理、代码与下一问 |
| 评价与辨析 | [评分标准](07-interview-evaluation-criteria.md) X01–X08 | 合格/深入/错误表达、八项能力边界、自评 |

共有36道主问题、8道专门辨析题、六条各六层追问链。追问链复用主问题知识，不将其虚报为36个全新知识点。

| 模块/主题 | 基础与实现 | 原理与权衡 | 场景与连续追问 |
| --- | --- | --- | --- |
| E4 编排 | O02、A01、B09 | D01 | S05、T1 |
| E1 验证/评测 | A04、A05 | X03、D03 | S04、T2 |
| E2 恢复 | A06 | D02、X01/X04 | S01/S03、T3 |
| E3 预算/生命周期 | B01–B03 | B08、D03 | S02/S04/S08、T4 |
| E5 工具/文件 | A02 | X05 | S05、T5 |
| E6 上下文 | A03、A07 | D03、D05 | S02、A07追问 |
| E7 订单 | B04–B07 | D04、X06 | S06/S07、T6 |
| E8 模型协议 | A08 | D05、X02 | S02/S03 |
| AI工程观测/生产边界 | A09、O03 | X08 | S04/S08 |
| 个人经历 | O04/O05 | 第三阶段复盘 | 需本人补充，不代写贡献 |

## 学习顺序

P0必须掌握：O01–O05、A01–A06/A08、B01/B02/B04–B06、D01/D04、S01/S02/S06及八项辨析。先讲具体实现，再讲原理；尚未确认的 O05 只准备事实清单。

P1重点准备：其余中高级实现、故障与权衡问题；沿六个案例深入。P2为集群、多Agent、远端副作用等扩展，不要抢在当前实现前讲。每题已标优先级与难度，树中逐层标注。

## 代码证据代号

每题代号指向以下具体文件与符号；精确类/方法行号沿用[第二阶段源码索引](../02-core-technical-deep-dive/source-index.md)。同一原理只在一个主题主讲，其他题通过编号继续追问。

| 代号 | 当前代码与定位符号 | 测试入口 |
| --- | --- | --- |
| R 架构 | [ApplicationRuntime](G:/program/CodingDev/devpilot/devpilot/application/runtime.py)、[bootstrap](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py)、[RuntimePort](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py)、[build_graph](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/graph.py)、shared/steps.py:observe_step/verify_step | devpilot/tests/runtime/test_graph_topology.py、test_graph_business_contracts.py；test_application_entrypoints.py |
| V 验证 | [TaskVerifier.verify/coverage_for](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py)、[capture_snapshot/materialize_candidate](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py)、[run_independent_suite](G:/program/CodingDev/devpilot/devpilot/testing/suite.py) | devpilot/tests/verification/test_evidence.py、test_verifier.py |
| E 评测 | [EvalRunner.run_eval](G:/program/CodingDev/devpilot/devpilot/evals/runner.py) | devpilot/tests/test_eval_truthfulness.py、test_hidden_test_isolation.py |
| J 恢复 | [OperationJournal](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py)、[runner.resume/_reconcile_model_requests/_publish_terminal](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py)、[checkpointer](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py)、[manifest](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py) | devpilot/tests/runtime/test_operation_journal.py、test_graph_resume.py、test_model_reconciliation.py、test_terminal_publication.py、test_verification_receipts.py |
| B 预算 | [RunBudget](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py)、[ExecutionSteps.decide_step](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py)、[执行服务](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py)、[RunLock/容量](G:/program/CodingDev/devpilot/devpilot/storage.py) | devpilot/tests/runtime/test_request_budget.py、test_recovery.py |
| P 进程 | [run_cancellable/run_process](G:/program/CodingDev/devpilot/devpilot/processes.py) | devpilot/tests/test_processes.py |
| F 文件 | [ToolRegistry](G:/program/CodingDev/devpilot/devpilot/tools/registry.py)、[PathGuard](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py)、[ApplyPatch](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py)、[SandboxWorkspace](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py) | devpilot/tests/tools/test_registry.py、test_path_guard.py、test_patch_atomicity.py；test_persistence.py |
| C 上下文 | [ContextBuilder](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py)、[StateManager](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py) | devpilot/tests/runtime/test_context_feedback.py、test_repair_loop.py；test_context_compression.py |
| M 模型 | [AgentDecision](G:/program/CodingDev/devpilot/devpilot/domain/decision.py)、[LangChainLLMClient](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py)、[prepare_messages](G:/program/CodingDev/devpilot/devpilot/llm/protocol.py)、[parse_decision](G:/program/CodingDev/devpilot/devpilot/llm/decision_parser.py) | devpilot/tests/llm/test_langchain_transport.py；domain/test_models.py |
| D 订单 | [OrderService](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py)、[update_stock](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py)、[transition_status](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py)、[get_db](G:/program/CodingDev/shopflow-order-service/app/db/database.py) | shopflow-order-service/tests/services/test_order_integrity.py |
| L 观测 | [TraceWriter](G:/program/CodingDev/devpilot/devpilot/tracing/writer.py)、[事件身份](G:/program/CodingDev/devpilot/devpilot/tracing/identity.py)、[模型记录](G:/program/CodingDev/devpilot/devpilot/llm/base.py) | devpilot/tests/tracing/test_identity.py |

## 原理资料与核查边界

本轮补充核对 [Python 3.12 asyncio](https://docs.python.org/3.12/library/asyncio-task.html)、[SQLite 隔离](https://www.sqlite.org/isolation.html)、[PostgreSQL 隔离](https://www.postgresql.org/docs/current/transaction-iso.html) 的官方说明，分别支撑取消/任务组合、单写者与数据库迁移扩展。PostgreSQL、TaskGroup 多任务方案是知识扩展，不是当前已用架构。

本轮为文档与源码静态核查，没有重新运行测试、真实模型或压测；测试路径说明已有断言依据，不等于本轮新增通过结果。沿用第三阶段修正：并发支付和并发取消测试不是混合竞争测试。对个人排查经历、真实选型试验、使用规模和效果指标仍需本人确认。
