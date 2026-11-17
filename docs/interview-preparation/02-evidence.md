# 证据索引与验证记录

基线 HEAD：`41c4ea517e12384a87bb11cb8ed0995aa995ba4a`。首次检查工作区无未提交变更。未发现仓库内 AGENTS.md。以下路径均相对仓库根目录，符号用于定位；索引覆盖本阶段重点，不表示全部源码逐行审计。

| 编号 | 实现路径及定位符号 | 交叉验证测试 |
| --- | --- | --- |
| E1 | `devpilot/devpilot/verification/verifier.py`：TaskVerifier.verify、coverage_for；`verification/evidence.py`；`evals/runner.py`：run_eval | `devpilot/tests/verification/test_verifier.py`；`test_eval_truthfulness.py`；`test_hidden_test_isolation.py` |
| E2 | `devpilot/devpilot/runtime/langgraph/operations.py`：OperationJournal.begin/complete；同目录 `runner.py`：_reconcile_model_requests、resume；`checkpointer.py`；`storage.py`：RunLock、atomic_write | `devpilot/tests/runtime/test_operation_journal.py`、`test_model_reconciliation.py`、`test_graph_resume.py`、`test_graph_process_kill.py` |
| E3 | `devpilot/devpilot/runtime/budget.py`：RunBudget；`runtime/shared/steps.py`：decide_step；`processes.py`：run_process、run_cancellable；`storage.py`：CapacityReservation | `devpilot/tests/runtime/test_request_budget.py`；`test_processes.py`；`test_p0_p2_boundaries.py` |
| E4 | `devpilot/devpilot/application/runtime.py`：ApplicationRuntime；`application/bootstrap.py`；`runtime/langgraph/graph.py`：build_graph；`runtime/shared/lifecycle.py`、`steps.py`；`settings.py:32` 默认配置 | `devpilot/tests/runtime/test_graph_topology.py`、`test_graph_business_contracts.py`、`test_legacy_routing.py`；`test_application_entrypoints.py` |
| E5 | `devpilot/devpilot/tools/path_guard.py`：validate_path；`tools/code/apply_patch.py`：ApplyPatch.execute；`workspace/sandbox.py` | `devpilot/tests/tools/test_patch_atomicity.py`、`test_path_guard.py`；`test_file_security.py` |
| E6 | `devpilot/devpilot/runtime/shared/context.py`：build、_enforce_limit、_compress_context；`runtime/shared/steps.py`：observe_step、verify_step | `devpilot/tests/test_context_compression.py`；`runtime/test_context_feedback.py`、`test_repair_loop.py` |
| E7 | `shopflow-order-service/app/services/order_service.py`；`app/repositories/product_repository.py`：update_stock；`order_repository.py`：transition_status、get_by_id | `shopflow-order-service/tests/services/test_order_integrity.py` |
| E8 | `devpilot/devpilot/llm/langchain.py`：LangChainLLMClient；`llm/decision_parser.py`：parse_decision；`domain/decision.py` | `devpilot/tests/llm/test_langchain.py`、`test_langchain_transport.py`；`domain/test_models.py` |

测试清单列出可继续复核的入口；本轮实际细读了操作回执测试、恢复测试主要分支，读取了订单完整性等测试用例索引，并执行以下重点测试。不能将“有测试文件”视为其全部断言已人工审核。

## 本轮执行结果

日期：2026-11-09；Windows，本地已有虚拟环境；未调用真实模型、未请求远程付费服务。

在 `G:/program/CodingDev/devpilot` 执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/runtime/test_operation_journal.py tests/runtime/test_model_reconciliation.py tests/runtime/test_graph_topology.py -q
```

退出码 0，`13 passed in 5.42s`。覆盖回执复用/不确定性拒绝、参数及工作区漂移、结果写失败、模型恢复计账和图拓扑。

在 `G:/program/CodingDev/shopflow-order-service` 执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/services/test_order_integrity.py -q
```

退出码 0，`17 passed in 14.49s`。包括输入边界、重复商品合并、失败回滚、取消一次回补、并发下单及支付/取消场景。它验证本地测试条件下的行为，不证明任意数据库或生产负载下的性能。

本轮未重跑全量回归、进程强杀矩阵、wheel 安装、确定性 benchmark 或真实模型能力评估。

## 历史材料使用规则

- `git show 34e6e7e -- .../product_repository.py .../order_repository.py`：确认从独立 commit/读改写改为 flush/条件更新，属于已查看差异的历史事实。
- `git show --stat 41c4ea5` 与当前图、适配器、共享服务代码：确认迁移涉及面；不可据此推断某人的工作时长或独立贡献。
- `docs/refactor-langgraph-langchain-langfuse-2026-10-29/remaining-gates.md`：历史验收范围、Windows 结果、Linux 未验证及 Langfuse 延期。
- 同目录 `performance-decision.md`：历史测量口径及局限；原始样本未在本轮重新核算，因此不将数据作为新增实测成果。
- 根 README 仅用于定位业务意图；涉及框架、补丁策略、隔离保证的内容以当前代码为准。
