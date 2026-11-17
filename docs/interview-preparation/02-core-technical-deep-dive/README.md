# 第二阶段：核心技术实现深度解析

日期：2026-11-09；源码基线：`41c4ea517e12384a87bb11cb8ed0995aa995ba4a`。已先读取第一阶段评估，再检查当前实现。DevPilot 与 ShopFlow 分开分析；历史动机、个人贡献及实际生产效果仍需本人确认。

## 阅读导航

| 顺序 | 文档 | 主线源码 | 应掌握的核心 |
| --- | --- | --- | --- |
| 1 / E4 | [双运行时](01-runtime-architecture.md) | application、contracts、shared、graph | 应用契约、依赖生命周期、编排与业务分离 |
| 2 / E1 | [可信验证](02-trusted-verification.md) | verification、testing、evals | 可信基线、候选物化、证据口径 |
| 3 / E2 | [恢复一致性](03-recovery-consistency.md) | langgraph/runner、operations、checkpointer | 崩溃窗口、结果复用、不确定性 |
| 4 / E3 | [预算生命周期](04-budget-lifecycle.md) | budget、steps、services、processes | 全局预算、取消传播、资源所有权 |
| 5 / E7 | [订单事务](05-order-transaction.md) | ShopFlow orders、Service、Repository | 条件更新、事务边界、幂等差异 |
| 6 / E5 | [受控文件修改](06-controlled-file-modification.md) | Registry、PathGuard、ApplyPatch | 参数与路径校验、补丁回滚、安全边界 |
| 7 / E6 | [上下文与修复](07-agent-context-management.md) | context、state_manager、steps | 状态投影、有损压缩、反馈优先级 |
| 8 / E8 | [模型协议](08-model-adapter-protocol.md) | llm、decision、DeveloperAgent | 分层验证、适配、重试计账 |
| 9 | [跨模块分析](09-cross-module-analysis.md) | 完整执行链 | 职责边界、故障归属、系统推演 |

[源码位置索引](source-index.md) 提供文件、类/方法及自动核对的定义行号。每篇正文沿调用链解释，不把索引当 API 手册。纯后端方向可在 E4 后先读 E7，再读 E3/E2；AI 应用方向按默认顺序。

## 验证记录

本轮在 DevPilot 虚拟环境执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/runtime/test_graph_business_contracts.py tests/runtime/test_operation_journal.py tests/runtime/test_model_reconciliation.py tests/runtime/test_context_feedback.py tests/llm/test_langchain.py tests/tools/test_registry.py -q
```

结果：退出码 0，**43 passed in 251.58s**。覆盖图运行时复用业务断言、回执与模型对账、最新反馈、模型协议和工具注册执行。测试采用 Fake/测试替身，不证明真实模型能力或生产可靠性。本文引用其他测试作为继续阅读和核查入口，不声称本轮重跑全部测试。

第一阶段订单完整性 17 项通过的记录仍保留在上级证据文档；本轮未重复执行。未运行真实模型、全量 CI、Linux 验证或生产压测；未修改业务代码。

## 使用方法与事实边界

每篇先读流程，再对照 source-index 的源码位置，最后用异常表推演失败路径。完成标准是能解释输入、状态变化、持久化位置、失败结果和替代方案，而不是背函数名。

原理补充与当前实现分开标注；Python 取消、SQLAlchemy Session、SQLite 单写者和 LangGraph 重执行相关内容参考正文中的官方资料。优化建议均未实施。对第一阶段摘要的细化集中记录在跨模块文档，尤其注意工具和模型恢复策略不同、commit 后 rollback 的限制及 Registry 的异常传播。
