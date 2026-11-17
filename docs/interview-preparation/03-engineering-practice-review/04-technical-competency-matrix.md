# 岗位能力证明矩阵

“能够体现”指项目提供可讨论证据，并非已证明求职者独立完成。个人贡献确认后才能改为第一人称成果。

| 专业能力 | 项目 | 实际技术实现 | 源码或测试证据 | 能够体现的能力 | 面试价值 |
| --- | --- | --- | --- | --- | --- |
| Agent 编排 | DevPilot | 图节点调用共享步骤，单分支路由 | runtime/langgraph/graph.py；test_graph_business_contracts.py | 定义控制流、迁移时保持业务契约 | 高 |
| AI 验证与评测 | DevPilot | 冻结候选、独立测试、smoke/capability | verification/evidence.py；evals/runner.py；test_eval_truthfulness.py | 将“生成”与“可信成功”分离 | 极高 |
| 结构化模型输入后端 | DevPilot | AgentDecision 和工具参数分层校验 | domain/decision.py；tools/registry.py；llm/test_langchain.py | 将模型输出当外部数据治理 | 中，作为支撑 |
| 上下文工程 | DevPilot | 最新反馈、repair_sources、硬字符限制 | runtime/shared/context.py；test_context_feedback.py | 保留当前失败事实、识别压缩代价 | 中高 |
| 持久化与恢复 | DevPilot | 回执、manifest、摘要、模型对账 | operations.py；test_operation_journal.py；test_model_reconciliation.py | 识别崩溃窗口和恢复准入 | 极高 |
| Python 异步生命周期 | DevPilot | shield、Event、等待 worker 清理 | processes.py；test_cancellation_waits_for_owned_process_cleanup | 区分 Task 取消与资源终止 | 高 |
| 预算治理 | DevPilot | 全局 deadline、累计验证时间、请求次数 | runtime/budget.py；test_request_budget.py；test_recovery.py | 避免重试/恢复重置成本约束 | 高 |
| 模块化架构 | DevPilot | RuntimePort、应用装配、RunOutcome | application/runtime.py；test_application_entrypoints.py | 隔离入口和运行时、管理依赖寿命 | 高 |
| 文件与 Git 工程 | DevPilot | 路径规范化、受保护文件、Git 预检与回滚 | tools/code/apply_patch.py；test_patch_atomicity.py；test_persistence.py | 处理非数据库副作用和文件边界 | 中高 |
| 事务和并发 | ShopFlow | 合并数量、条件库存、统一提交 | order_service.py；product_repository.py；test_failure_rolls_back_everything | 根据不变量划分事务 | 极高（后端） |
| 状态与幂等 | ShopFlow | 状态 CAS、重复取消不重复回补 | order_repository.py；test_cancellation_restores_stock_once | 区分状态迁移和请求级幂等 | 高 |
| API 与会话生命周期 | ShopFlow | Depends(get_db)、异常映射、finally close | app/api/orders.py；app/db/database.py | 基本分层、HTTP 语义、资源释放 | 基础 |
| 回归与发行验证 | DevPilot/ShopFlow，职责分开 | Fake、故障注入、基准、wheel 检查与 CI | .github/workflows/ci.yml；scripts/check_wheel.py；各自 tests | 可重复验证和源码外安装检查意识 | 中高；不证明远端 CI 已成功 |
| 配置与本地观测 | DevPilot | Settings、Trace、请求记录、脱敏 | settings.py；tracing/writer.py；llm/base.py | 运行诊断和配置边界 | 中；非生产监控平台 |

源码精确行号见[索引](../02-core-technical-deep-dive/source-index.md)，本表 DevPilot 路径默认相对 devpilot/devpilot，测试相对 devpilot/tests；ShopFlow 相对 shopflow-order-service/app 或 tests。

## 两个方向的展示组合

AI 应用：E1 → E2 → E4/E3，最后用 E6/E8 说明模型输出如何进入受控闭环。与简单 API 接入的区别是运行状态、工具副作用、验证证据和成本都由后端约束；仍不涉及模型训练或算法效果创新。

Python 后端：E7 → E3 → E2/E4。订单案例说明单库事务，Agent 平台说明异步资源和跨资源恢复，必须点明两者不共享同一事务或服务数据库。

## 缺乏证据的能力

不补写大规模分布式调度、真实支付退款、多租户安全、生产 SLO、向量 RAG、模型训练、Kubernetes 部署或商业规模。Docker/生产部署不是为了覆盖岗位要求而添加的履历项。个人解决问题的能力还需通过复现过程和解释能力确认。
