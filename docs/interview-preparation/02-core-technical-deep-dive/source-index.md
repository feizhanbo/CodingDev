# 源码位置索引

基线 41c4ea5；2026-11-09 从当前源码 AST 提取定义行号。链接使用绝对路径；正文按文件和符号引用此索引。此表是定位辅助，不表示每个函数都属于重点分析。

## devpilot/devpilot/application/runtime.py

| 定义 | 源码位置 |
| --- | --- |
| `ApplicationRuntime` | [L10](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:10) |
| `ApplicationRuntime.__init__` | [L11](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:11) |
| `ApplicationRuntime._build` | [L15](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:15) |
| `ApplicationRuntime.execute` | [L21](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:21) |
| `ApplicationRuntime.resume` | [L25](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:25) |
| `artifact_store` | [L54](G:/program/CodingDev/devpilot/devpilot/application/runtime.py:54) |

## devpilot/devpilot/application/factory.py

| 定义 | 源码位置 |
| --- | --- |
| `create_runtime` | [L7](G:/program/CodingDev/devpilot/devpilot/application/factory.py:7) |

## devpilot/devpilot/application/bootstrap.py

| 定义 | 源码位置 |
| --- | --- |
| `load_issue` | [L39](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py:39) |
| `register_all_tools` | [L68](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py:68) |
| `smoke_repository` | [L88](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py:88) |
| `create_fake_client` | [L92](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py:92) |
| `initialize_components` | [L130](G:/program/CodingDev/devpilot/devpilot/application/bootstrap.py:130) |

## devpilot/devpilot/runtime/contracts.py

| 定义 | 源码位置 |
| --- | --- |
| `FrozenPolicy` | [L11](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:11) |
| `FrozenPolicy.from_config` | [L15](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:15) |
| `FrozenPolicy.config` | [L20](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:20) |
| `WorkspaceStart` | [L27](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:27) |
| `RunRequest` | [L34](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:34) |
| `RunOutcome` | [L42](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:42) |
| `RuntimePort` | [L53](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:53) |
| `RuntimePort.execute` | [L54](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:54) |
| `RuntimePort.resume` | [L55](G:/program/CodingDev/devpilot/devpilot/runtime/contracts.py:55) |

## devpilot/devpilot/runtime/shared/lifecycle.py

| 定义 | 源码位置 |
| --- | --- |
| `RuntimeLifecycle` | [L60](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:60) |
| `RuntimeLifecycle.__init__` | [L65](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:65) |
| `RuntimeLifecycle._emit` | [L103](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:103) |
| `RuntimeLifecycle._trace` | [L112](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:112) |
| `RuntimeLifecycle._enrich_test_failure` | [L145](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:145) |
| `RuntimeLifecycle._outcome` | [L173](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:173) |
| `RuntimeLifecycle.run_outcome` | [L191](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:191) |
| `RuntimeLifecycle.resume_outcome` | [L195](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:195) |
| `RuntimeLifecycle.run` | [L198](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:198) |
| `RuntimeLifecycle.resume` | [L213](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:213) |
| `RuntimeLifecycle._run_exclusive` | [L262](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:262) |
| `RuntimeLifecycle._run` | [L273](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:273) |
| `RuntimeLifecycle._execute_loop` | [L436](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:436) |
| `RuntimeLifecycle._prepare` | [L439](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:439) |
| `RuntimeLifecycle._remaining` | [L462](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:462) |
| `RuntimeLifecycle._maybe_advance_phase` | [L470](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:470) |
| `RuntimeLifecycle._build_result` | [L509](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:509) |
| `RuntimeLifecycle._save_artifacts` | [L540](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:540) |
| `RuntimeLifecycle._checkpoint` | [L622](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:622) |
| `_session_property` | [L656](G:/program/CodingDev/devpilot/devpilot/runtime/shared/lifecycle.py:656) |

## devpilot/devpilot/runtime/shared/steps.py

| 定义 | 源码位置 |
| --- | --- |
| `BudgetExceeded` | [L13](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:13) |
| `ExecutionSteps` | [L17](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:17) |
| `ExecutionSteps._verify_candidate` | [L18](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:18) |
| `ExecutionSteps._begin_model_request` | [L24](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:24) |
| `ExecutionSteps._end_model_request` | [L27](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:27) |
| `ExecutionSteps.decide_step` | [L30](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:30) |
| `ExecutionSteps.execute_tool_step` | [L78](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:78) |
| `ExecutionSteps.plan_feedback_step` | [L129](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:129) |
| `ExecutionSteps.observe_step` | [L181](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:181) |
| `ExecutionSteps.verify_step` | [L259](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:259) |
| `ExecutionSteps.max_steps_step` | [L385](G:/program/CodingDev/devpilot/devpilot/runtime/shared/steps.py:385) |

## devpilot/devpilot/runtime/shared/services.py

| 定义 | 源码位置 |
| --- | --- |
| `DecisionService` | [L8](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:8) |
| `DecisionService.decide` | [L9](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:9) |
| `ToolExecutionService` | [L17](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:17) |
| `ToolExecutionService.execute` | [L18](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:18) |
| `AcceptanceService` | [L30](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:30) |
| `AcceptanceService.verify` | [L31](G:/program/CodingDev/devpilot/devpilot/runtime/shared/services.py:31) |

## devpilot/devpilot/runtime/shared/state_manager.py

| 定义 | 源码位置 |
| --- | --- |
| `StateManager` | [L23](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:23) |
| `StateManager.__init__` | [L26](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:26) |
| `StateManager.create` | [L29](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:29) |
| `StateManager.transition_phase` | [L38](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:38) |
| `StateManager.add_observation` | [L45](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:45) |
| `StateManager.apply_tool_result` | [L51](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:51) |
| `StateManager.request_completion` | [L88](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:88) |
| `StateManager.reject_verification` | [L92](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:92) |
| `StateManager.set_repair` | [L112](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:112) |
| `StateManager.increment_retry` | [L121](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:121) |
| `StateManager.serialize` | [L125](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:125) |
| `StateManager.deserialize` | [L129](G:/program/CodingDev/devpilot/devpilot/runtime/shared/state_manager.py:129) |

## devpilot/devpilot/runtime/shared/context.py

| 定义 | 源码位置 |
| --- | --- |
| `ContextBuilder` | [L53](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:53) |
| `ContextBuilder.__init__` | [L56](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:56) |
| `ContextBuilder.build` | [L69](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:69) |
| `ContextBuilder._enforce_limit` | [L103](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:103) |
| `ContextBuilder._build_task_content` | [L146](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:146) |
| `ContextBuilder._build_state_content` | [L157](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:157) |
| `ContextBuilder._summarize_observations` | [L256](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:256) |
| `ContextBuilder._build_progress_summary` | [L265](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:265) |
| `ContextBuilder._format_observation_data` | [L351](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:351) |
| `ContextBuilder._format_test_failure_block` | [L426](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:426) |
| `ContextBuilder._truncate` | [L454](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:454) |
| `ContextBuilder._compress_context` | [L460](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:460) |
| `ContextBuilder._get_phase_instruction` | [L485](G:/program/CodingDev/devpilot/devpilot/runtime/shared/context.py:485) |

## devpilot/devpilot/runtime/custom/runner.py

| 定义 | 源码位置 |
| --- | --- |
| `CustomAgentRunner` | [L13](G:/program/CodingDev/devpilot/devpilot/runtime/custom/runner.py:13) |
| `CustomAgentRunner._execute_loop` | [L16](G:/program/CodingDev/devpilot/devpilot/runtime/custom/runner.py:16) |

## devpilot/devpilot/runtime/langgraph/graph.py

| 定义 | 源码位置 |
| --- | --- |
| `GraphState` | [L10](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/graph.py:10) |
| `build_graph` | [L33](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/graph.py:33) |

## devpilot/devpilot/runtime/langgraph/runner.py

| 定义 | 源码位置 |
| --- | --- |
| `LangGraphAgentRunner` | [L38](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:38) |
| `LangGraphAgentRunner._save_artifacts` | [L41](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:41) |
| `LangGraphAgentRunner._emit` | [L47](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:47) |
| `LangGraphAgentRunner._trace` | [L56](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:56) |
| `LangGraphAgentRunner._publish_terminal` | [L71](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:71) |
| `LangGraphAgentRunner._verify_candidate` | [L90](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:90) |
| `LangGraphAgentRunner._begin_model_request` | [L131](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:131) |
| `LangGraphAgentRunner._end_model_request` | [L146](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:146) |
| `LangGraphAgentRunner._reconcile_model_requests` | [L165](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:165) |
| `LangGraphAgentRunner.decide_step` | [L208](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:208) |
| `LangGraphAgentRunner.resume` | [L214](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:214) |
| `LangGraphAgentRunner._execute_loop` | [L263](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/runner.py:263) |

## devpilot/devpilot/runtime/langgraph/operations.py

| 定义 | 源码位置 |
| --- | --- |
| `ManualRecoveryRequired` | [L11](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:11) |
| `digest` | [L15](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:15) |
| `Receipt` | [L20](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:20) |
| `OperationJournal` | [L33](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:33) |
| `OperationJournal.__init__` | [L34](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:34) |
| `OperationJournal._name` | [L38](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:38) |
| `OperationJournal.read` | [L41](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:41) |
| `OperationJournal.begin` | [L52](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:52) |
| `OperationJournal.complete` | [L71](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:71) |
| `OperationJournal._save` | [L80](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/operations.py:80) |

## devpilot/devpilot/runtime/langgraph/checkpointer.py

| 定义 | 源码位置 |
| --- | --- |
| `QuotaSqliteSaver` | [L11](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:11) |
| `QuotaSqliteSaver.__init__` | [L12](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:12) |
| `QuotaSqliteSaver.reservation` | [L18](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:18) |
| `QuotaSqliteSaver.aput` | [L24](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:24) |
| `QuotaSqliteSaver.aput_writes` | [L33](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:33) |
| `open_checkpointer` | [L41](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/checkpointer.py:41) |

## devpilot/devpilot/runtime/langgraph/recovery.py

| 定义 | 源码位置 |
| --- | --- |
| `checkpoint_from_graph` | [L6](G:/program/CodingDev/devpilot/devpilot/runtime/langgraph/recovery.py:6) |

## devpilot/devpilot/runtime/manifest.py

| 定义 | 源码位置 |
| --- | --- |
| `RunManifest` | [L12](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py:12) |
| `manifest_for` | [L21](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py:21) |
| `read_manifest` | [L40](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py:40) |
| `validate_manifest` | [L55](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py:55) |
| `read_legacy_checkpoint` | [L61](G:/program/CodingDev/devpilot/devpilot/runtime/manifest.py:61) |

## devpilot/devpilot/runtime/budget.py

| 定义 | 源码位置 |
| --- | --- |
| `RunBudget` | [L11](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py:11) |
| `RunBudget.start` | [L19](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py:19) |
| `RunBudget.remaining` | [L33](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py:33) |
| `RunBudget.evaluation` | [L40](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py:40) |
| `RunBudget.snapshot` | [L52](G:/program/CodingDev/devpilot/devpilot/runtime/budget.py:52) |

## devpilot/devpilot/verification/evidence.py

| 定义 | 源码位置 |
| --- | --- |
| `is_test` | [L31](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:31) |
| `protected` | [L36](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:36) |
| `inventory` | [L41](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:41) |
| `capture_snapshot` | [L62](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:62) |
| `read_manifest` | [L84](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:84) |
| `validate_write` | [L88](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:88) |
| `check_integrity` | [L104](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:104) |
| `materialize_candidate` | [L118](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:118) |

## devpilot/devpilot/verification/verifier.py

| 定义 | 源码位置 |
| --- | --- |
| `VerificationResult` | [L26](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:26) |
| `TaskVerifier` | [L36](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:36) |
| `TaskVerifier.__init__` | [L39](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:39) |
| `TaskVerifier._timeout` | [L45](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:45) |
| `TaskVerifier.bind_snapshot` | [L53](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:53) |
| `TaskVerifier.verify` | [L56](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:56) |
| `TaskVerifier._check_visible_tests` | [L211](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:211) |
| `TaskVerifier._check_diff_non_empty` | [L237](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:237) |
| `TaskVerifier._check_forbidden_files` | [L267](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:267) |
| `TaskVerifier._check_modified_file_count` | [L284](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:284) |
| `coverage_for` | [L300](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:300) |

## devpilot/devpilot/testing/suite.py

| 定义 | 源码位置 |
| --- | --- |
| `has_behavior_assertions` | [L15](G:/program/CodingDev/devpilot/devpilot/testing/suite.py:15) |
| `run_independent_suite` | [L40](G:/program/CodingDev/devpilot/devpilot/testing/suite.py:40) |

## devpilot/devpilot/testing/junit.py

| 定义 | 源码位置 |
| --- | --- |
| `SuiteResult` | [L7](G:/program/CodingDev/devpilot/devpilot/testing/junit.py:7) |
| `parse_junit` | [L22](G:/program/CodingDev/devpilot/devpilot/testing/junit.py:22) |

## devpilot/devpilot/processes.py

| 定义 | 源码位置 |
| --- | --- |
| `WindowsJob` | [L26](G:/program/CodingDev/devpilot/devpilot/processes.py:26) |
| `WindowsJob.__init__` | [L29](G:/program/CodingDev/devpilot/devpilot/processes.py:29) |
| `WindowsJob.close` | [L86](G:/program/CodingDev/devpilot/devpilot/processes.py:86) |
| `ProcessResult` | [L93](G:/program/CodingDev/devpilot/devpilot/processes.py:93) |
| `ProcessResult.returncode` | [L103](G:/program/CodingDev/devpilot/devpilot/processes.py:103) |
| `run_process` | [L107](G:/program/CodingDev/devpilot/devpilot/processes.py:107) |
| `capture_process` | [L282](G:/program/CodingDev/devpilot/devpilot/processes.py:282) |
| `capture_process_async` | [L323](G:/program/CodingDev/devpilot/devpilot/processes.py:323) |
| `run_process_async` | [L327](G:/program/CodingDev/devpilot/devpilot/processes.py:327) |
| `run_cancellable` | [L331](G:/program/CodingDev/devpilot/devpilot/processes.py:331) |
| `run_sync` | [L352](G:/program/CodingDev/devpilot/devpilot/processes.py:352) |

## devpilot/devpilot/storage.py

| 定义 | 源码位置 |
| --- | --- |
| `ArtifactQuotaExceeded` | [L12](G:/program/CodingDev/devpilot/devpilot/storage.py:12) |
| `tree_bytes` | [L16](G:/program/CodingDev/devpilot/devpilot/storage.py:16) |
| `RunLock` | [L38](G:/program/CodingDev/devpilot/devpilot/storage.py:38) |
| `RunLock.__init__` | [L41](G:/program/CodingDev/devpilot/devpilot/storage.py:41) |
| `RunLock.__enter__` | [L44](G:/program/CodingDev/devpilot/devpilot/storage.py:44) |
| `RunLock.__exit__` | [L67](G:/program/CodingDev/devpilot/devpilot/storage.py:67) |
| `atomic_write` | [L82](G:/program/CodingDev/devpilot/devpilot/storage.py:82) |
| `CapacityReservation` | [L98](G:/program/CodingDev/devpilot/devpilot/storage.py:98) |
| `CapacityReservation.__init__` | [L106](G:/program/CodingDev/devpilot/devpilot/storage.py:106) |
| `CapacityReservation.check` | [L116](G:/program/CodingDev/devpilot/devpilot/storage.py:116) |
| `CapacityReservation.__enter__` | [L124](G:/program/CodingDev/devpilot/devpilot/storage.py:124) |
| `CapacityReservation.__exit__` | [L150](G:/program/CodingDev/devpilot/devpilot/storage.py:150) |
| `check_active_capacity` | [L166](G:/program/CodingDev/devpilot/devpilot/storage.py:166) |

## devpilot/devpilot/agents/developer.py

| 定义 | 源码位置 |
| --- | --- |
| `DeveloperAgent` | [L14](G:/program/CodingDev/devpilot/devpilot/agents/developer.py:14) |
| `DeveloperAgent.__init__` | [L17](G:/program/CodingDev/devpilot/devpilot/agents/developer.py:17) |
| `DeveloperAgent.decide` | [L22](G:/program/CodingDev/devpilot/devpilot/agents/developer.py:22) |

## devpilot/devpilot/llm/base.py

| 定义 | 源码位置 |
| --- | --- |
| `ContextBudgetExceeded` | [L13](G:/program/CodingDev/devpilot/devpilot/llm/base.py:13) |
| `LLMMessage` | [L17](G:/program/CodingDev/devpilot/devpilot/llm/base.py:17) |
| `LLMResponse` | [L24](G:/program/CodingDev/devpilot/devpilot/llm/base.py:24) |
| `LLMRequestRecord` | [L34](G:/program/CodingDev/devpilot/devpilot/llm/base.py:34) |
| `LLMClient` | [L47](G:/program/CodingDev/devpilot/devpilot/llm/base.py:47) |
| `LLMClient.chat` | [L53](G:/program/CodingDev/devpilot/devpilot/llm/base.py:53) |

## devpilot/devpilot/llm/langchain.py

| 定义 | 源码位置 |
| --- | --- |
| `_RequestEvents` | [L14](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:14) |
| `_RequestEvents.__init__` | [L19](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:19) |
| `_RequestEvents.on_llm_error` | [L22](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:22) |
| `LangChainLLMClient` | [L26](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:26) |
| `LangChainLLMClient.__init__` | [L29](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:29) |
| `LangChainLLMClient.chat` | [L45](G:/program/CodingDev/devpilot/devpilot/llm/langchain.py:45) |

## devpilot/devpilot/llm/openai.py

| 定义 | 源码位置 |
| --- | --- |
| `OpenAIClient` | [L22](G:/program/CodingDev/devpilot/devpilot/llm/openai.py:22) |
| `OpenAIClient.__init__` | [L34](G:/program/CodingDev/devpilot/devpilot/llm/openai.py:34) |
| `OpenAIClient.chat` | [L41](G:/program/CodingDev/devpilot/devpilot/llm/openai.py:41) |

## devpilot/devpilot/llm/fake.py

| 定义 | 源码位置 |
| --- | --- |
| `FakeLLMClient` | [L8](G:/program/CodingDev/devpilot/devpilot/llm/fake.py:8) |
| `FakeLLMClient.__init__` | [L11](G:/program/CodingDev/devpilot/devpilot/llm/fake.py:11) |
| `FakeLLMClient.chat` | [L16](G:/program/CodingDev/devpilot/devpilot/llm/fake.py:16) |

## devpilot/devpilot/llm/protocol.py

| 定义 | 源码位置 |
| --- | --- |
| `prepare_messages` | [L21](G:/program/CodingDev/devpilot/devpilot/llm/protocol.py:21) |

## devpilot/devpilot/llm/decision_parser.py

| 定义 | 源码位置 |
| --- | --- |
| `parse_decision` | [L6](G:/program/CodingDev/devpilot/devpilot/llm/decision_parser.py:6) |

## devpilot/devpilot/domain/decision.py

| 定义 | 源码位置 |
| --- | --- |
| `ToolAction` | [L12](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:12) |
| `FinishIntent` | [L19](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:19) |
| `AgentDecision` | [L26](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:26) |
| `AgentDecision.exactly_one_branch` | [L34](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:34) |

## devpilot/devpilot/tools/registry.py

| 定义 | 源码位置 |
| --- | --- |
| `ToolRegistry` | [L17](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:17) |
| `ToolRegistry.__init__` | [L20](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:20) |
| `ToolRegistry.register` | [L24](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:24) |
| `ToolRegistry.get` | [L35](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:35) |
| `ToolRegistry.canonical_name` | [L38](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:38) |
| `ToolRegistry.execute` | [L42](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:42) |
| `ToolRegistry.list_schemas` | [L85](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:85) |
| `ToolRegistry.names` | [L97](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:97) |

## devpilot/devpilot/tools/path_guard.py

| 定义 | 源码位置 |
| --- | --- |
| `PathGuard` | [L20](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:20) |
| `PathGuard.__init__` | [L26](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:26) |
| `PathGuard.validate_path` | [L32](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:32) |
| `PathGuard._check_symlinks` | [L60](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:60) |
| `PathGuard._check_forbidden` | [L75](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:75) |

## devpilot/devpilot/tools/code/apply_patch.py

| 定义 | 源码位置 |
| --- | --- |
| `ApplyPatchInput` | [L17](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:17) |
| `ApplyPatch` | [L23](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:23) |
| `ApplyPatch.execute` | [L43](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:43) |
| `_GitResult` | [L123](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:123) |
| `_run_git` | [L129](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:129) |
| `_modified_files` | [L135](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:135) |
| `_extract_paths` | [L142](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:142) |

## devpilot/devpilot/evals/runner.py

| 定义 | 源码位置 |
| --- | --- |
| `EvalResult` | [L36](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:36) |
| `EvalRunner` | [L66](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:66) |
| `EvalRunner.__init__` | [L69](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:69) |
| `EvalRunner.run_eval` | [L101](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:101) |
| `EvalRunner._persist_evaluation` | [L243](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:243) |
| `EvalRunner.run_all` | [L263](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:263) |
| `EvalRunner._init_components` | [L277](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:277) |
| `EvalRunner._check_visible_tests` | [L289](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:289) |
| `EvalRunner._run_hidden_tests` | [L317](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:317) |
| `EvalRunner._load_state` | [L372](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:372) |
| `EvalRunner._collect_metrics` | [L391](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:391) |
| `EvalRunner._save_final_diff` | [L395](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:395) |
| `EvalRunner._calculate_change_scope` | [L416](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:416) |
| `EvalRunner.generate_summary` | [L428](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:428) |
| `EvalRunner.generate_comparison_table` | [L481](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:481) |
| `_first_int` | [L512](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:512) |

## shopflow-order-service/app/api/orders.py

| 定义 | 源码位置 |
| --- | --- |
| `create_order` | [L15](G:/program/CodingDev/shopflow-order-service/app/api/orders.py:15) |
| `get_orders` | [L28](G:/program/CodingDev/shopflow-order-service/app/api/orders.py:28) |
| `get_order` | [L37](G:/program/CodingDev/shopflow-order-service/app/api/orders.py:37) |
| `pay_order` | [L50](G:/program/CodingDev/shopflow-order-service/app/api/orders.py:50) |
| `cancel_order` | [L66](G:/program/CodingDev/shopflow-order-service/app/api/orders.py:66) |

## shopflow-order-service/app/db/database.py

| 定义 | 源码位置 |
| --- | --- |
| `Base` | [L12](G:/program/CodingDev/shopflow-order-service/app/db/database.py:12) |
| `get_db` | [L17](G:/program/CodingDev/shopflow-order-service/app/db/database.py:17) |

## shopflow-order-service/app/services/order_service.py

| 定义 | 源码位置 |
| --- | --- |
| `OrderService` | [L13](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:13) |
| `OrderService.create_order` | [L17](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:17) |
| `OrderService.get_order` | [L62](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:62) |
| `OrderService.get_orders` | [L71](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:71) |
| `OrderService.pay_order` | [L82](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:82) |
| `OrderService.cancel_order` | [L98](G:/program/CodingDev/shopflow-order-service/app/services/order_service.py:98) |

## shopflow-order-service/app/repositories/order_repository.py

| 定义 | 源码位置 |
| --- | --- |
| `OrderRepository` | [L10](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:10) |
| `OrderRepository.__init__` | [L13](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:13) |
| `OrderRepository.create` | [L16](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:16) |
| `OrderRepository.get_by_id` | [L36](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:36) |
| `OrderRepository.get_all` | [L45](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:45) |
| `OrderRepository.update_status` | [L49](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:49) |
| `OrderRepository.transition_status` | [L58](G:/program/CodingDev/shopflow-order-service/app/repositories/order_repository.py:58) |

## shopflow-order-service/app/repositories/product_repository.py

| 定义 | 源码位置 |
| --- | --- |
| `ProductRepository` | [L9](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py:9) |
| `ProductRepository.__init__` | [L12](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py:12) |
| `ProductRepository.get_by_id` | [L15](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py:15) |
| `ProductRepository.get_all` | [L19](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py:19) |
| `ProductRepository.update_stock` | [L23](G:/program/CodingDev/shopflow-order-service/app/repositories/product_repository.py:23) |
