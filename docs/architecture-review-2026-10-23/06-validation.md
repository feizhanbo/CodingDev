# 验证记录与源码索引

日期：2026-10-23，Windows / PowerShell，Python 3.12.13，解释器 `G:/program/CodingDev/devpilot/.venv/Scripts/python.exe`。工作区 commit：`2341ca172109f544cb35bb5adf9abdc39df46cbc`。以工作区文件为准，git diff 未显示已跟踪源文件修改。

## 实际执行

在 `G:/program/CodingDev/devpilot` 执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

结果：**500 passed, 2 failed, 2 skipped, 1 warning，467.18 秒**（504 项）。不得描述为全绿。使用现有测试与 Fake/mock，测试在临时样例仓库执行文件/Git/pytest 操作；没有启动真实模型 capability eval。

失败详情：

|用例|失败位置/解释|
|---|---|
|`tests/runtime/test_recovery.py::test_ready_boundary_restores_test_retry_and_repair_history`|第 280 行 `checkpoint.read_text()` 未指定编码，GBK 解码 UTF-8 内容失败；尚未执行到后续恢复断言|
|`tests/test_eval_truthfulness.py::test_evaluation_disk_failure_returns_redacted_fallback`|第 91 行 `Path(result.recovery_file).read_text()` 未指定编码，GBK 解码失败；不是断言发现明文 secret 泄露|

源码中的实际 resume 与 artifact 保存使用显式 UTF-8；需在 P0 修复测试可移植性并保留默认 locale 覆盖，不能用更换全局环境掩盖测试代码问题。定向诊断命令：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m pytest tests/runtime/test_recovery.py::test_ready_boundary_restores_test_retry_and_repair_history tests/test_eval_truthfulness.py::test_evaluation_disk_failure_returns_redacted_fallback -q -p no:cacheprovider
```

定向结果见下方追加记录；即使复测通过也不改写首次全量测试的 2 失败事实。

收集警告：Pydantic `TestRun` 带构造器，pytest 不将其作为测试类收集。全量输出未打印 skip reason，因此不把两项跳过冒称已验证；源码有受符号链接权限影响的 skip 分支。本轮没有为取得覆盖率更改系统权限。

## 只读诊断探针

使用 RuntimeConfig 默认值、空 ToolRegistry，构造 description 为 40,000 个 x 的 DevelopmentTask；ContextBuilder.build 返回总 content 字符数 **44,298**，max_context_chars 为 **30,000**。证实该阈值不是硬上限，不是实际模型费用测试。

对新建 understanding 状态调用 StateManager.transition_phase(..., 'implementing')，得到 **Invalid phase transition: understanding -> implementing**。结合 runner 验收拒绝分支的 suppress(ValueError) 构成静态问题证据；没有声称探针独立跑通了完整拒绝/修复流程。

未执行：框架安装/PoC、真实模型能力 A/B、生产级隔离对抗、全部八题 benchmark reference 正负对照和 performance 全量重验。因此不能从这次 pytest 推导所有隐藏测试业务覆盖完备、性能达标或框架已验证。现有 benchmark 单测验证资源绑定、输入可重现、JUnit 语义和独立 harness，迁移门槛仍要求完整正负对照。

## 证据使用规则

01–02 的当前代码结论对应以下源码符号；03 的外部能力附官方链接；04–05 明确为未来设计。源码索引按本轮文件自动提取 AST 行号，支持定位而非证明覆盖率。源码哈希用于辨认本报告基线，不记录 `.env` 或密钥。

## 定向复测结果

UTF-8 模式定向复测：**2 passed in 9.42s**。两项失败定位为测试读取编码问题；未重跑整套测试，未修改测试源文件。


## 源码符号定位

|文件/符号|行号|
|---|---|
|[devpilot/devpilot/agents/developer.py — DeveloperAgent](G:/program/CodingDev/devpilot/devpilot/agents/developer.py:14)|14|
|[devpilot/devpilot/cli.py — _callback](G:/program/CodingDev/devpilot/devpilot/cli.py:48)|48|
|[devpilot/devpilot/cli.py — load_issue](G:/program/CodingDev/devpilot/devpilot/cli.py:52)|52|
|[devpilot/devpilot/cli.py — register_all_tools](G:/program/CodingDev/devpilot/devpilot/cli.py:81)|81|
|[devpilot/devpilot/cli.py — smoke_repository](G:/program/CodingDev/devpilot/devpilot/cli.py:101)|101|
|[devpilot/devpilot/cli.py — create_fake_client](G:/program/CodingDev/devpilot/devpilot/cli.py:105)|105|
|[devpilot/devpilot/cli.py — initialize_components](G:/program/CodingDev/devpilot/devpilot/cli.py:143)|143|
|[devpilot/devpilot/cli.py — _format_tool_result](G:/program/CodingDev/devpilot/devpilot/cli.py:207)|207|
|[devpilot/devpilot/cli.py — _make_rich_callback](G:/program/CodingDev/devpilot/devpilot/cli.py:230)|230|
|[devpilot/devpilot/cli.py — _display_summary](G:/program/CodingDev/devpilot/devpilot/cli.py:280)|280|
|[devpilot/devpilot/cli.py — run](G:/program/CodingDev/devpilot/devpilot/cli.py:309)|309|
|[devpilot/devpilot/cli.py — resume](G:/program/CodingDev/devpilot/devpilot/cli.py:350)|350|
|[devpilot/devpilot/cli.py — inspect](G:/program/CodingDev/devpilot/devpilot/cli.py:375)|375|
|[devpilot/devpilot/cli.py — diff](G:/program/CodingDev/devpilot/devpilot/cli.py:492)|492|
|[devpilot/devpilot/cli.py — eval](G:/program/CodingDev/devpilot/devpilot/cli.py:537)|537|
|[devpilot/devpilot/cli.py — benchmark_check](G:/program/CodingDev/devpilot/devpilot/cli.py:584)|584|
|[devpilot/devpilot/cli.py — workspace_report](G:/program/CodingDev/devpilot/devpilot/cli.py:606)|606|
|[devpilot/devpilot/domain/decision.py — ToolAction](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:12)|12|
|[devpilot/devpilot/domain/decision.py — FinishIntent](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:19)|19|
|[devpilot/devpilot/domain/decision.py — AgentDecision](G:/program/CodingDev/devpilot/devpilot/domain/decision.py:26)|26|
|[devpilot/devpilot/domain/plan.py — PlanStep](G:/program/CodingDev/devpilot/devpilot/domain/plan.py:10)|10|
|[devpilot/devpilot/domain/plan.py — ImplementationPlan](G:/program/CodingDev/devpilot/devpilot/domain/plan.py:36)|36|
|[devpilot/devpilot/domain/result.py — AgentRunResult](G:/program/CodingDev/devpilot/devpilot/domain/result.py:12)|12|
|[devpilot/devpilot/domain/state.py — Observation](G:/program/CodingDev/devpilot/devpilot/domain/state.py:13)|13|
|[devpilot/devpilot/domain/state.py — TestRun](G:/program/CodingDev/devpilot/devpilot/domain/state.py:25)|25|
|[devpilot/devpilot/domain/state.py — DevPilotState](G:/program/CodingDev/devpilot/devpilot/domain/state.py:37)|37|
|[devpilot/devpilot/domain/task.py — DevelopmentTask](G:/program/CodingDev/devpilot/devpilot/domain/task.py:10)|10|
|[devpilot/devpilot/evals/benchmark.py — SuiteResult](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:30)|30|
|[devpilot/devpilot/evals/benchmark.py — digest](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:45)|45|
|[devpilot/devpilot/evals/benchmark.py — resource_root](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:49)|49|
|[devpilot/devpilot/evals/benchmark.py — packaged_baseline](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:53)|53|
|[devpilot/devpilot/evals/benchmark.py — load_manifest](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:57)|57|
|[devpilot/devpilot/evals/benchmark.py — _safe_child](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:61)|61|
|[devpilot/devpilot/evals/benchmark.py — _run_git](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:68)|68|
|[devpilot/devpilot/evals/benchmark.py — verify_resources](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:81)|81|
|[devpilot/devpilot/evals/benchmark.py — apply_dataset_patch](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:91)|91|
|[devpilot/devpilot/evals/benchmark.py — prepare_task](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:105)|105|
|[devpilot/devpilot/evals/benchmark.py — parse_junit](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:138)|138|
|[devpilot/devpilot/evals/benchmark.py — has_behavior_assertions](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:184)|184|
|[devpilot/devpilot/evals/benchmark.py — run_independent_suite](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:209)|209|
|[devpilot/devpilot/evals/benchmark.py — validate_benchmark](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:315)|315|
|[devpilot/devpilot/evals/benchmark.py — BenchmarkWorkspace](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:376)|376|
|[devpilot/devpilot/evals/benchmark.py — main](G:/program/CodingDev/devpilot/devpilot/evals/benchmark.py:394)|394|
|[devpilot/devpilot/evals/metrics.py — collect_metrics](G:/program/CodingDev/devpilot/devpilot/evals/metrics.py:9)|9|
|[devpilot/devpilot/evals/runner.py — EvalResult](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:32)|32|
|[devpilot/devpilot/evals/runner.py — EvalRunner](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:61)|61|
|[devpilot/devpilot/evals/runner.py — _first_int](G:/program/CodingDev/devpilot/devpilot/evals/runner.py:476)|476|
|[devpilot/devpilot/evals/shared/conftest.py — override_get_db](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:24)|24|
|[devpilot/devpilot/evals/shared/conftest.py — TestClient](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:36)|36|
|[devpilot/devpilot/evals/shared/conftest.py — _seed_data](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:62)|62|
|[devpilot/devpilot/evals/shared/conftest.py — db_session](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:114)|114|
|[devpilot/devpilot/evals/shared/conftest.py — seeded_session](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:126)|126|
|[devpilot/devpilot/evals/shared/conftest.py — client](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:139)|139|
|[devpilot/devpilot/evals/shared/conftest.py — seeded_client](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:151)|151|
|[devpilot/devpilot/evals/shared/conftest.py — session_factory](G:/program/CodingDev/devpilot/devpilot/evals/shared/conftest.py:167)|167|
|[devpilot/devpilot/llm/base.py — LLMMessage](G:/program/CodingDev/devpilot/devpilot/llm/base.py:13)|13|
|[devpilot/devpilot/llm/base.py — LLMResponse](G:/program/CodingDev/devpilot/devpilot/llm/base.py:20)|20|
|[devpilot/devpilot/llm/base.py — LLMRequestRecord](G:/program/CodingDev/devpilot/devpilot/llm/base.py:30)|30|
|[devpilot/devpilot/llm/base.py — LLMClient](G:/program/CodingDev/devpilot/devpilot/llm/base.py:43)|43|
|[devpilot/devpilot/llm/config.py — LLMConfig](G:/program/CodingDev/devpilot/devpilot/llm/config.py:8)|8|
|[devpilot/devpilot/llm/fake.py — FakeLLMClient](G:/program/CodingDev/devpilot/devpilot/llm/fake.py:8)|8|
|[devpilot/devpilot/llm/openai.py — OpenAIClient](G:/program/CodingDev/devpilot/devpilot/llm/openai.py:17)|17|
|[devpilot/devpilot/llm/prompts.py — build_system_prompt](G:/program/CodingDev/devpilot/devpilot/llm/prompts.py:91)|91|
|[devpilot/devpilot/llm/tool_schema.py — tools_to_openai_format](G:/program/CodingDev/devpilot/devpilot/llm/tool_schema.py:7)|7|
|[devpilot/devpilot/processes.py — WindowsJob](G:/program/CodingDev/devpilot/devpilot/processes.py:23)|23|
|[devpilot/devpilot/processes.py — ProcessResult](G:/program/CodingDev/devpilot/devpilot/processes.py:90)|90|
|[devpilot/devpilot/processes.py — run_process](G:/program/CodingDev/devpilot/devpilot/processes.py:98)|98|
|[devpilot/devpilot/processes.py — run_process_async](G:/program/CodingDev/devpilot/devpilot/processes.py:246)|246|
|[devpilot/devpilot/processes.py — run_cancellable](G:/program/CodingDev/devpilot/devpilot/processes.py:250)|250|
|[devpilot/devpilot/runtime/base.py — AgentRunner](G:/program/CodingDev/devpilot/devpilot/runtime/base.py:13)|13|
|[devpilot/devpilot/runtime/base.py — RuntimeConfig](G:/program/CodingDev/devpilot/devpilot/runtime/base.py:24)|24|
|[devpilot/devpilot/runtime/custom/context.py — ContextBuilder](G:/program/CodingDev/devpilot/devpilot/runtime/custom/context.py:53)|53|
|[devpilot/devpilot/runtime/custom/loop_guard.py — GuardrailViolation](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:15)|15|
|[devpilot/devpilot/runtime/custom/loop_guard.py — MaxStepsExceeded](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:19)|19|
|[devpilot/devpilot/runtime/custom/loop_guard.py — MaxRetriesExceeded](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:23)|23|
|[devpilot/devpilot/runtime/custom/loop_guard.py — DuplicateActionDetected](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:27)|27|
|[devpilot/devpilot/runtime/custom/loop_guard.py — MaxModifiedFilesExceeded](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:31)|31|
|[devpilot/devpilot/runtime/custom/loop_guard.py — _decision_type](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:35)|35|
|[devpilot/devpilot/runtime/custom/loop_guard.py — LoopGuard](G:/program/CodingDev/devpilot/devpilot/runtime/custom/loop_guard.py:46)|46|
|[devpilot/devpilot/runtime/custom/recovery.py — Checkpoint](G:/program/CodingDev/devpilot/devpilot/runtime/custom/recovery.py:21)|21|
|[devpilot/devpilot/runtime/custom/recovery.py — validate_run_id](G:/program/CodingDev/devpilot/devpilot/runtime/custom/recovery.py:43)|43|
|[devpilot/devpilot/runtime/custom/recovery.py — recovery_inventory](G:/program/CodingDev/devpilot/devpilot/runtime/custom/recovery.py:48)|48|
|[devpilot/devpilot/runtime/custom/recovery.py — runtime_identity](G:/program/CodingDev/devpilot/devpilot/runtime/custom/recovery.py:70)|70|
|[devpilot/devpilot/runtime/custom/recovery.py — restore_fields](G:/program/CodingDev/devpilot/devpilot/runtime/custom/recovery.py:95)|95|
|[devpilot/devpilot/runtime/custom/runner.py — BudgetExceeded](G:/program/CodingDev/devpilot/devpilot/runtime/custom/runner.py:49)|49|
|[devpilot/devpilot/runtime/custom/runner.py — CustomAgentRunner](G:/program/CodingDev/devpilot/devpilot/runtime/custom/runner.py:53)|53|
|[devpilot/devpilot/runtime/custom/state_manager.py — StateManager](G:/program/CodingDev/devpilot/devpilot/runtime/custom/state_manager.py:23)|23|
|[devpilot/devpilot/security.py — forbidden](G:/program/CodingDev/devpilot/devpilot/security.py:22)|22|
|[devpilot/devpilot/security.py — linked](G:/program/CodingDev/devpilot/devpilot/security.py:31)|31|
|[devpilot/devpilot/security.py — permitted_files](G:/program/CodingDev/devpilot/devpilot/security.py:35)|35|
|[devpilot/devpilot/security.py — process_environment](G:/program/CodingDev/devpilot/devpilot/security.py:56)|56|
|[devpilot/devpilot/security.py — redact](G:/program/CodingDev/devpilot/devpilot/security.py:64)|64|
|[devpilot/devpilot/settings.py — Settings](G:/program/CodingDev/devpilot/devpilot/settings.py:16)|16|
|[devpilot/devpilot/storage.py — ArtifactQuotaExceeded](G:/program/CodingDev/devpilot/devpilot/storage.py:10)|10|
|[devpilot/devpilot/storage.py — tree_bytes](G:/program/CodingDev/devpilot/devpilot/storage.py:14)|14|
|[devpilot/devpilot/storage.py — RunLock](G:/program/CodingDev/devpilot/devpilot/storage.py:31)|31|
|[devpilot/devpilot/storage.py — atomic_write](G:/program/CodingDev/devpilot/devpilot/storage.py:75)|75|
|[devpilot/devpilot/tools/base.py — Tool](G:/program/CodingDev/devpilot/devpilot/tools/base.py:12)|12|
|[devpilot/devpilot/tools/code/apply_patch.py — ApplyPatchInput](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:17)|17|
|[devpilot/devpilot/tools/code/apply_patch.py — ApplyPatch](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:23)|23|
|[devpilot/devpilot/tools/code/apply_patch.py — _GitResult](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:117)|117|
|[devpilot/devpilot/tools/code/apply_patch.py — _run_git](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:123)|123|
|[devpilot/devpilot/tools/code/apply_patch.py — _modified_files](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:140)|140|
|[devpilot/devpilot/tools/code/apply_patch.py — _extract_paths](G:/program/CodingDev/devpilot/devpilot/tools/code/apply_patch.py:156)|156|
|[devpilot/devpilot/tools/code/create_file.py — CreateFileInput](G:/program/CodingDev/devpilot/devpilot/tools/code/create_file.py:16)|16|
|[devpilot/devpilot/tools/code/create_file.py — CreateFile](G:/program/CodingDev/devpilot/devpilot/tools/code/create_file.py:23)|23|
|[devpilot/devpilot/tools/code/create_file.py — _write_file](G:/program/CodingDev/devpilot/devpilot/tools/code/create_file.py:75)|75|
|[devpilot/devpilot/tools/code/create_file.py — _git_add](G:/program/CodingDev/devpilot/devpilot/tools/code/create_file.py:82)|82|
|[devpilot/devpilot/tools/code/create_file.py — _relative](G:/program/CodingDev/devpilot/devpilot/tools/code/create_file.py:98)|98|
|[devpilot/devpilot/tools/context.py — ToolContext](G:/program/CodingDev/devpilot/devpilot/tools/context.py:10)|10|
|[devpilot/devpilot/tools/context.py — ToolResult](G:/program/CodingDev/devpilot/devpilot/tools/context.py:28)|28|
|[devpilot/devpilot/tools/git/diff.py — GitDiffInput](G:/program/CodingDev/devpilot/devpilot/tools/git/diff.py:14)|14|
|[devpilot/devpilot/tools/git/diff.py — GitDiff](G:/program/CodingDev/devpilot/devpilot/tools/git/diff.py:20)|20|
|[devpilot/devpilot/tools/git/diff.py — _run](G:/program/CodingDev/devpilot/devpilot/tools/git/diff.py:59)|59|
|[devpilot/devpilot/tools/git/status.py — GitStatusInput](G:/program/CodingDev/devpilot/devpilot/tools/git/status.py:13)|13|
|[devpilot/devpilot/tools/git/status.py — GitStatus](G:/program/CodingDev/devpilot/devpilot/tools/git/status.py:17)|17|
|[devpilot/devpilot/tools/git/status.py — _run](G:/program/CodingDev/devpilot/devpilot/tools/git/status.py:52)|52|
|[devpilot/devpilot/tools/path_guard.py — PathGuard](G:/program/CodingDev/devpilot/devpilot/tools/path_guard.py:20)|20|
|[devpilot/devpilot/tools/registry.py — ToolRegistry](G:/program/CodingDev/devpilot/devpilot/tools/registry.py:15)|15|
|[devpilot/devpilot/tools/repo/file_cache.py — ReadFileCache](G:/program/CodingDev/devpilot/devpilot/tools/repo/file_cache.py:11)|11|
|[devpilot/devpilot/tools/repo/list_files.py — ListFilesInput](G:/program/CodingDev/devpilot/devpilot/tools/repo/list_files.py:26)|26|
|[devpilot/devpilot/tools/repo/list_files.py — ListFiles](G:/program/CodingDev/devpilot/devpilot/tools/repo/list_files.py:33)|33|
|[devpilot/devpilot/tools/repo/list_files.py — _walk_sync](G:/program/CodingDev/devpilot/devpilot/tools/repo/list_files.py:76)|76|
|[devpilot/devpilot/tools/repo/read_file.py — ReadFileInput](G:/program/CodingDev/devpilot/devpilot/tools/repo/read_file.py:18)|18|
|[devpilot/devpilot/tools/repo/read_file.py — ReadFile](G:/program/CodingDev/devpilot/devpilot/tools/repo/read_file.py:26)|26|
|[devpilot/devpilot/tools/repo/read_file.py — _relative](G:/program/CodingDev/devpilot/devpilot/tools/repo/read_file.py:106)|106|
|[devpilot/devpilot/tools/repo/search_code.py — SearchCodeInput](G:/program/CodingDev/devpilot/devpilot/tools/repo/search_code.py:27)|27|
|[devpilot/devpilot/tools/repo/search_code.py — SearchCode](G:/program/CodingDev/devpilot/devpilot/tools/repo/search_code.py:36)|36|
|[devpilot/devpilot/tools/test/failure_parser.py — parse_test_failures](G:/program/CodingDev/devpilot/devpilot/tools/test/failure_parser.py:33)|33|
|[devpilot/devpilot/tools/test/failure_parser.py — _is_covered](G:/program/CodingDev/devpilot/devpilot/tools/test/failure_parser.py:124)|124|
|[devpilot/devpilot/tools/test/failure_parser.py — _extract_traceback_locations](G:/program/CodingDev/devpilot/devpilot/tools/test/failure_parser.py:132)|132|
|[devpilot/devpilot/tools/test/run_tests.py — RunTestsInput](G:/program/CodingDev/devpilot/devpilot/tools/test/run_tests.py:21)|21|
|[devpilot/devpilot/tools/test/run_tests.py — RunTests](G:/program/CodingDev/devpilot/devpilot/tools/test/run_tests.py:28)|28|
|[devpilot/devpilot/tools/test/run_tests.py — _log_path](G:/program/CodingDev/devpilot/devpilot/tools/test/run_tests.py:166)|166|
|[devpilot/devpilot/tools/test/run_tests.py — _validate_extra_args](G:/program/CodingDev/devpilot/devpilot/tools/test/run_tests.py:176)|176|
|[devpilot/devpilot/tracing/events.py — TraceEvent](G:/program/CodingDev/devpilot/devpilot/tracing/events.py:11)|11|
|[devpilot/devpilot/tracing/events.py — _now_iso](G:/program/CodingDev/devpilot/devpilot/tracing/events.py:31)|31|
|[devpilot/devpilot/tracing/metrics.py — MetricsCollector](G:/program/CodingDev/devpilot/devpilot/tracing/metrics.py:8)|8|
|[devpilot/devpilot/tracing/writer.py — TraceWriter](G:/program/CodingDev/devpilot/devpilot/tracing/writer.py:12)|12|
|[devpilot/devpilot/verification/__init__.py — __getattr__](G:/program/CodingDev/devpilot/devpilot/verification/__init__.py:13)|13|
|[devpilot/devpilot/verification/evidence.py — is_test](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:30)|30|
|[devpilot/devpilot/verification/evidence.py — protected](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:35)|35|
|[devpilot/devpilot/verification/evidence.py — inventory](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:40)|40|
|[devpilot/devpilot/verification/evidence.py — capture_snapshot](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:62)|62|
|[devpilot/devpilot/verification/evidence.py — read_manifest](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:84)|84|
|[devpilot/devpilot/verification/evidence.py — validate_write](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:88)|88|
|[devpilot/devpilot/verification/evidence.py — check_integrity](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:104)|104|
|[devpilot/devpilot/verification/evidence.py — materialize_candidate](G:/program/CodingDev/devpilot/devpilot/verification/evidence.py:118)|118|
|[devpilot/devpilot/verification/verifier.py — VerificationResult](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:26)|26|
|[devpilot/devpilot/verification/verifier.py — TaskVerifier](G:/program/CodingDev/devpilot/devpilot/verification/verifier.py:34)|34|
|[devpilot/devpilot/workspace/config.py — WorkspaceConfig](G:/program/CodingDev/devpilot/devpilot/workspace/config.py:7)|7|
|[devpilot/devpilot/workspace/sandbox.py — SandboxWorkspace](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py:22)|22|
|[devpilot/devpilot/workspace/sandbox.py — _on_rmtree_error](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py:154)|154|
|[devpilot/devpilot/workspace/sandbox.py — _detect_symlinks](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py:166)|166|
|[devpilot/devpilot/workspace/sandbox.py — _git_init](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py:184)|184|
|[devpilot/devpilot/workspace/sandbox.py — _git](G:/program/CodingDev/devpilot/devpilot/workspace/sandbox.py:195)|195|

## 源文件 SHA-256

|文件|SHA-256|
|---|---|
|`devpilot/devpilot/__init__.py`|`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`|
|`devpilot/devpilot/agents/__init__.py`|`1cbc1b40043afba2b982705f15d3a4d6d2ccc70134ae75e0a981e0c846ca0ba2`|
|`devpilot/devpilot/agents/developer.py`|`3329d7b587704e6922b0150d4d48041ca06f1567d4a6c7a6405ba27475ee0cf2`|
|`devpilot/devpilot/cli.py`|`495d80c064632d3f5e42442b3586b0dd57ac5e4dbbf363212baf4a307c73e47f`|
|`devpilot/devpilot/domain/__init__.py`|`9f25de325c3b031a8b81f8b36178d6023f4dadb20bb5b31e93eaeedf4aa3b922`|
|`devpilot/devpilot/domain/decision.py`|`36e1db93322c3f9081d4ae3e3624542f1411022b8c0d67f43e084df522e770b3`|
|`devpilot/devpilot/domain/plan.py`|`c29cfa034979e16da94aea57b6cdad230238363186ebbb5314688b39ea1a75f4`|
|`devpilot/devpilot/domain/result.py`|`274ff8ef4d7a725c41288ca34b6a46eac72428a0b30ddf91858b288644c1d743`|
|`devpilot/devpilot/domain/state.py`|`a18ffddcae4424b4aada8afb508f2ac7ae4e08f77a57b72b9e8c3d29ce8359bb`|
|`devpilot/devpilot/domain/task.py`|`b1087b803d45c944af1d9fe746e2e637a701e62865770d95b0afc864c5aac677`|
|`devpilot/devpilot/evals/__init__.py`|`fc8cfb9f3ccb1ee2f68c42f97f63a35b8e615e949619c1f88a923bc6b77d91c2`|
|`devpilot/devpilot/evals/benchmark.py`|`c9d68b8014c3cba1c3fa278f5c14bb83b1991237303636309e2cdc3c5918ef38`|
|`devpilot/devpilot/evals/metrics.py`|`4addcb544ec3f59bf0aac63dba45df3ae77ac83e91c712037ac194fd2abac0a5`|
|`devpilot/devpilot/evals/runner.py`|`54df3d89cfbd3480c7f907a117a7dd758e1361259984d11e1105acda0b53b394`|
|`devpilot/devpilot/evals/shared/conftest.py`|`6adf63f3c99f3dae7a54ad00b230b70f811eebb3c22e615fd2e0d9f014e2884c`|
|`devpilot/devpilot/llm/__init__.py`|`bcb8b38931d2c2b3e155ce3014eecb069d777b8725001a560bdf9b6939969bb0`|
|`devpilot/devpilot/llm/base.py`|`140fa16c87464db4e2bb9cd9fe9dbfc48a08880cb35f3710bba8ed6241d3eee0`|
|`devpilot/devpilot/llm/config.py`|`0eb81997a6542ff00fe241d626592760ef4d94bf025a0d07979ad5df3e5d34cd`|
|`devpilot/devpilot/llm/fake.py`|`00b1edb1372a60a86c8507ecb96664a8cb1191d567e370410c76666a7876bd99`|
|`devpilot/devpilot/llm/openai.py`|`8cc7d96520665da54710cbb22bc755e66ce53b2f958479626f6794d4f68884fb`|
|`devpilot/devpilot/llm/prompts.py`|`7461902635d46890fa6e451d1b6639174b0d1168cb1244ece9e647d04ede843e`|
|`devpilot/devpilot/llm/tool_schema.py`|`c62fa76c0eab773e287ee343c7866c9a253b96e828c929290e388d6c558e414e`|
|`devpilot/devpilot/processes.py`|`408e904c3b7e8a63d7a13377f1e534dd52ee3df2165190bd1b2978a525b647c0`|
|`devpilot/devpilot/runtime/__init__.py`|`08437ca4c49efd68c71fa17ac392797a091dc7c0a69c88aa75d2233b0e92272d`|
|`devpilot/devpilot/runtime/base.py`|`ff4eb904539ad9008f229b999c9a732ba69f40ee2e9669b3ba4e99ea2161c1e5`|
|`devpilot/devpilot/runtime/custom/__init__.py`|`93d9ac6e13f2c74611e7873ba5821bbe3c5c1bbf20e96ec9932a590067817778`|
|`devpilot/devpilot/runtime/custom/context.py`|`9211aed59518906593c10bd252c59981e6ef7a63b151a4b1be4cd335f904f713`|
|`devpilot/devpilot/runtime/custom/loop_guard.py`|`d85ed3255d25d2ac44638141cfc8f8f77352244f0038ab283476071ceade4386`|
|`devpilot/devpilot/runtime/custom/recovery.py`|`94b326a953f56e571dc27723938eab38178355480c8b026d6af687a922b9e86c`|
|`devpilot/devpilot/runtime/custom/runner.py`|`3f1aee5c461d3625c10f60b1d0db52aab4d014efe0197d0e95d252ecc7e1b892`|
|`devpilot/devpilot/runtime/custom/state_manager.py`|`084a5533122e860e2bc9fae0c0067da5d4de711434a9974b1803b5ff6ae784bb`|
|`devpilot/devpilot/security.py`|`bff61d0a41eec50c5008ee522e130d0823586147eff1235648b3c8ed9e7a6ee0`|
|`devpilot/devpilot/settings.py`|`b10faf074f153e68eed4364b910e11acefd2dfd6dfa10fef94afa18d956014a4`|
|`devpilot/devpilot/storage.py`|`12a279c0e920f70157609c7e1b2fc4f75bb93e6637b13be7b7d5376703c0f1cc`|
|`devpilot/devpilot/tools/__init__.py`|`e95190d5914d277a57e35bb5aca4c86fff13f1c4efc861693d863e3e2219bb4f`|
|`devpilot/devpilot/tools/base.py`|`d16face85181e3dd16537388dff0270660c7929a5cd1cc2c6172d7fd89102ed7`|
|`devpilot/devpilot/tools/code/__init__.py`|`2737b8f8eb9ae64ab6555e4770f3e54f4d0107a098c5f06b247e674814d00340`|
|`devpilot/devpilot/tools/code/apply_patch.py`|`2a3ccf8a103eee974d2ede765b12a7adf198d88c45ab2fd851fe143009d44abd`|
|`devpilot/devpilot/tools/code/create_file.py`|`868fe9c23dd2266325a522bdab2e788503fa1e5adc83d56f2956babaa3bd341e`|
|`devpilot/devpilot/tools/context.py`|`66a2c9893df3732cbc4627f5a7e2be5ce1af97161796bb2824db3d4d9052bfdb`|
|`devpilot/devpilot/tools/git/__init__.py`|`786949991e2caed058e5100ea81af166e8ca151b3553e7fb451643ca4b7e1080`|
|`devpilot/devpilot/tools/git/diff.py`|`3e068532154458b95adf8fe73c125f58565e35753d208603e9fc24a296f2d705`|
|`devpilot/devpilot/tools/git/status.py`|`0c96f2215b819875012ef486a60ccd42dca9bc31146161d12199aee626194678`|
|`devpilot/devpilot/tools/path_guard.py`|`6acd296d5a0b5a6b2ced9981a2d57083a821b5bff88f2930d8392f52f7f78958`|
|`devpilot/devpilot/tools/registry.py`|`1d5943f3214b997513cf3e20632b2117463917b73b0d3382b0319246086335a3`|
|`devpilot/devpilot/tools/repo/__init__.py`|`10a2679046d08540c83689412c4012cab46deba5e2cb07eecd51527b3ee2bfc3`|
|`devpilot/devpilot/tools/repo/file_cache.py`|`0d82edb559752d84493df8d059e1b9e27434e9f99f2d5b7a37b1691e3e00429b`|
|`devpilot/devpilot/tools/repo/list_files.py`|`e38eba4187fe18dff393533081c120d5e9959eab110351b3835a631efdf0273c`|
|`devpilot/devpilot/tools/repo/read_file.py`|`f3736e11fba356d4efb613fa7703458c5749b9e590996cd83ef2c3e9db00ce48`|
|`devpilot/devpilot/tools/repo/search_code.py`|`20d9b9c56caf55e9b575887f99f233e176c1831053be1b7062c99a7a9e191e6f`|
|`devpilot/devpilot/tools/test/__init__.py`|`3e15df6280db22cecae59b3f9e85df1e4a0817905ce56bf11b4b051142a440cb`|
|`devpilot/devpilot/tools/test/failure_parser.py`|`116585aa561ef6083f085550fe62f66cf56327b2346a6b9a11475d4cfa0b0335`|
|`devpilot/devpilot/tools/test/run_tests.py`|`febe00fb06792bc4e645091b048cb2df2a040885c5d8bfbacde7b03136463713`|
|`devpilot/devpilot/tracing/__init__.py`|`b0cdb6a8235cada5f5d7137a520a9abaea6e651dd0be151b2ce9229741b9ed5a`|
|`devpilot/devpilot/tracing/events.py`|`ed33d24bb3fcba727bfd96339f5d27448d7c28651446898e31f78a7e8c366451`|
|`devpilot/devpilot/tracing/metrics.py`|`e1d58ede0f701144f934bd4343ec996f1b14d68911d02dc48d6a67c8bc636d52`|
|`devpilot/devpilot/tracing/writer.py`|`70f189a3d10afb46a876d517486d5d2f64a95e1973e8a3ce520a53731d95f141`|
|`devpilot/devpilot/verification/__init__.py`|`79229382afed7941f45f88c351f32e416694d4e5f27404ee14602e89fd7b29e1`|
|`devpilot/devpilot/verification/evidence.py`|`bf786df87aa64ab327a994c040112a0dd5c17cd745b18141042d3df4085d10fd`|
|`devpilot/devpilot/verification/verifier.py`|`cb1910de0224f13679fd0a3ac678abc57544fc8307623eba401f2aabb3ae7274`|
|`devpilot/devpilot/workspace/__init__.py`|`238d7bc52bc8743381cd6fc68e739b52a9a06593b76d864a9b02b5d56a4a8354`|
|`devpilot/devpilot/workspace/config.py`|`ac07d4dd630252985a960b118d6d70592a69014f2813997dae4a147f8f464c84`|
|`devpilot/devpilot/workspace/sandbox.py`|`3b7854ba2f24ed4e94a835b2947e0184a485a9793000e5c54bdec5fb27f5633c`|
