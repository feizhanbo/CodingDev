# 本次验证记录与证据边界

日期：2026-10-24（Asia/Shanghai）。仓库：`G:/program/CodingDev`。Git HEAD：`41b027b4860354f69205ed7895de044b7f2bd39e`。

## 1. 执行范围与环境

读取有效源码、测试、依赖与 CI 配置；没有依赖历史审计报告形成结论。未读取或展示 `.env` 内容；测试只使用预置 Fake、mock 和临时仓库。本轮没有修改业务代码、测试代码、依赖文件或 ShopFlow 业务文件，没有调用收费模型，没有访问生产业务资源。候选框架仅查询官方资料，未安装或 PoC。

本机环境读取结果：

| 项目 | 版本 |
|---|---|
| Python | 3.12.13 / Windows AMD64 |
| Pydantic | 2.13.4 |
| pydantic-settings | 2.15.0 |
| OpenAI SDK | 3.5.0 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 |
| Ruff / Typer | 0.16.4 / 0.27.1 |

这是本机实际环境，不代表未来框架版本已与其验证兼容。CI 文件声明 Windows/Linux 矩阵，但本轮仅执行 Windows 本机验证，不能报告 Linux CI 已通过。

## 2. DevPilot 测试

在 `G:/program/CodingDev/devpilot` 使用已有虚拟环境执行：

```powershell
& 'G:/program/CodingDev/devpilot/.venv/Scripts/python.exe' -m pytest -q -p no:cacheprovider
```

已归档完整输出：[pytest-baseline.txt](G:/program/CodingDev/docs/architecture-review-2026-10-24/pytest-baseline.txt)。结果：**511 passed, 2 skipped, 1 warning，517.30 秒，退出码 0**。耗时受同时进行的审计/本机负载影响，不作为框架开销基线。

警告：`domain/state.py:25` 的 Pydantic `TestRun` 因有构造器被 pytest 收集时跳过为测试类；它是领域类型，不是缺失的运行测试。

为确认两项 skip 的原因，单独运行涉及链接的测试（不是重复整套测试）：

```powershell
& 'G:/program/CodingDev/devpilot/.venv/Scripts/python.exe' -m pytest -q -rs -p no:cacheprovider tests/test_file_security.py tests/tools/test_path_guard.py -k symlink
```

输出见 [skip-reasons.txt](G:/program/CodingDev/docs/architecture-review-2026-10-24/skip-reasons.txt)：当前环境不能创建相应符号链接，两项均 skip。故本轮不能以“511 通过”宣称这两个真实链接场景已验证；需在允许创建 symlink 的环境/CI 补齐。未为运行测试申请扩大系统权限。

收费模型阻断由 [tests/conftest.py](G:/program/CodingDev/devpilot/tests/conftest.py) 的 autouse fixture 替换 OpenAI 同步/异步 Chat Completions create 实现，并由 `test_paid_transport_is_blocked` 验证。测试中的真实文件、Git、pytest 操作发生在测试工作区，Fake 不代表工具被模拟。

关键覆盖与对应结论：

| 测试文件（根为 `G:/program/CodingDev/devpilot/tests`） | 支持的结论 | 不支持的外推 |
|---|---|---|
| `test_runtime_contract_baseline.py` | calculator 真修改→测试失败→修复→新增测试→独立验收；7 observations / 8 requests | 真实模型能够自主完成相同任务 |
| `runtime/test_request_budget.py, test_recovery.py` | 请求/恢复预算、未知 usage、deadline、漂移/执行中工具恢复拒绝、运行锁 | 所有 I/O 都已可取消，或已有通用持久人审 |
| `test_runtime_hardening.py, runtime/test_context_feedback.py` | 上下文硬限制、验收失败来源保存、别名冲突等 | 所有自然语言条件都已被验收 |
| `verification/test_verifier.py, test_evidence.py` | 冻结测试/配置完整性、候选构造与独立测试 | 防同用户恶意候选代码的 OS 安全隔离 |
| `test_processes.py` | 测试进程超时/输出/取消、Windows Job 生命周期 | Git/rg 已接入同一清理实现 |
| `test_hidden_test_isolation.py, test_file_security.py` | 工具路径隔离和内容过滤的已有覆盖 | Runner 缓存也在鉴权后读取（本次探针反例） |
| `test_eval_truthfulness.py, test_benchmark.py` | PASS/FAIL/ERROR/NOT_EVALUATED，固定资源、真实断言、独立配置 | Fake 成功等于 capability 成功 |
| `test_framework_independence.py` | import 层不直接依赖 custom 实现 | 运行时接口不再读取/修改 Runner 内部属性 |

## 3. 八任务 Benchmark 自检

使用现有 CLI `benchmark-check`，目标解释器为 ShopFlow 的既有虚拟环境。输出根为本轮新建临时目录，避免修改真实业务项目；摘要和命令输出复制到本报告目录。等价复现命令如下，output 必须使用新的临时目录：

```powershell
$auditOutput = Join-Path $env:TEMP ('devpilot-architecture-audit-' + [guid]::NewGuid().ToString('N'))
& 'G:/program/CodingDev/devpilot/.venv/Scripts/python.exe' -m devpilot.cli benchmark-check --test-python 'G:/program/CodingDev/shopflow-order-service/.venv/Scripts/python.exe' --output $auditOutput
```

结果：dataset **v1.1**，status **completed**，passed **true**，8/8 自检通过，退出码 0。未开启 `--performance`，所以不包含硬件相关性能门槛。证据：[benchmark-summary.json](G:/program/CodingDev/docs/architecture-review-2026-10-24/benchmark-summary.json)、[命令输出](G:/program/CodingDev/docs/architecture-review-2026-10-24/benchmark-validation.txt)。摘要中的报告路径指向临时目录，原始 XML/log 可能随系统清理而失效；长期验收时应按迁移计划归档完整证据树。

| 任务 | 缺陷版本状态 / 断言失败数 | 参考修复隐藏测试通过数 | 参考修复可见测试通过数 |
|---|---|---:|---:|
| DEV-001 | FAIL / 10 | 11 | 51 |
| DEV-002 | FAIL / 5 | 9 | 51 |
| DEV-003 | FAIL / 3 | 12 | 51 |
| DEV-004 | FAIL / 4 | 13 | 51 |
| DEV-005 | FAIL / 3 | 7 | 51 |
| DEV-006 | FAIL / 4 | 5 | 51 |
| DEV-007 | FAIL / 5 | 6 | 51 |
| DEV-008 | FAIL / 3 | 3 | 51 |

“参考修复”来自可信数据集补丁，不是本轮由模型生成。该结果证明任务能检测已知缺陷、参考补丁和测试 harness 可运行；不构成 DevPilot 真实模型能力得分，也不是新旧 Runtime 对照（新 Runtime 尚未实现）。

## 4. 两个专项离线探针

输出见 [audit-probes.txt](G:/program/CodingDev/docs/architecture-review-2026-10-24/audit-probes.txt)。探针以进程内临时代码执行，没有将 Python 脚本添加到业务仓库。

### 缓存先读取再鉴权

方法：在临时 smoke 工作区父目录放置仅含合成文字的 `audit-sentinel.txt`；使用 FakeLLM 返回 `repo.read_file('../audit-sentinel.txt')`；在 `Path.read_bytes` 上设置 spy，只统计这个合成文件；运行真实 Runner，记录第一次工具观察。

结果：

```json
{"probe":"cache_before_pathguard","outside_file_reads":1,"first_tool_success":false,"tool_error":"Path '../audit-sentinel.txt' resolves outside workspace root","content_returned":false}
```

结论是“越界文件被读取一次后工具拒绝”，不是“秘密已泄露给模型”。没有使用真实敏感文件。后续 Fake 响应耗尽出现的两条重试 WARNING 来自探针只预置了一次动作，不影响首次动作边界结论。

最小复核要点：`runner.py:518–523` 拼路径并调用缓存；`file_cache.py:37` 附近在 PathGuard 执行前计算内容 hash；`ReadFile.execute` 的权限拒绝发生在这之后。修复测试应检查 spy 读取次数为零，而不只是报错字符串。

### 阶段推断可滞后真实动作

方法：创建 understanding 状态，依次调用 `_maybe_advance_phase`，传入合法结构的 code.create_file 与 test.run 决策；不执行真实写操作、不调用模型。

结果：

```json
{"probe":"direct_code_then_test_phase","phase":"understanding"}
```

此探针证明阶段转换函数本身的语义；结合 Runner 没有 phase-specific 工具准入限制，说明该路径可发生。它不是关于模型通常会如何选择动作的概率判断。

## 5. 静态审计与 lint

全包搜索五个配置项，只在 `settings.py` 与 `runtime/base.py` 找到声明/验证，没有执行端消费：tool_timeout_seconds、max_tool_output_bytes、preparation_timeout_seconds、evaluation_timeout_seconds、diagnostic_reserve_bytes。

核对调用顺序确认：准备完成后才设置 active deadline；普通工具 await 只使用 `_remaining()`；测试工具有独立有效输出/超时上限；Git/rg 工具未复用该进程执行器。以上为源码路径证据，不把未跑的极限故障场景写成已实测。

Ruff 命令：

```powershell
& 'G:/program/CodingDev/devpilot/.venv/Scripts/python.exe' -m ruff check devpilot tests --output-format concise
```

发现 **14 项现有问题**，未使用 `--fix`：

| 规则 | 位置（相对 DevPilot 项目根） |
|---|---|
| E501 | `devpilot/cli.py:295`、`devpilot/llm/openai.py:13`、`devpilot/runtime/custom/context.py:126`、`tests/runtime/test_recovery.py:61`、`tests/runtime/test_request_budget.py:48`、`tests/test_runtime_hardening.py:55`、`:139` |
| I001 | `devpilot/llm/openai.py:3`、`tests/runtime/test_repair_loop.py:13`、`test_runner.py:3`、`test_self_correction.py:3`、`tests/test_planning_flow.py:3`、`tests/test_runtime_hardening.py:3`、`tests/verifier_stub.py:2` |

因此可以报告测试基线通过，但不能报告 CI 全绿；CI 还包含 Ruff、ShopFlow 独立测试、wheel 构建/外部安装等，本轮未执行全部 CI。没有为了通过审计而调整断言、关闭安全测试或修改业务逻辑。

## 6. 证据强度和本轮未验证项

- **实测**：已有 pytest 套件、Benchmark 自检、两个合成探针、实际环境版本、Ruff 结果。
- **源码确认**：模块调用/依赖、配置未接入、主链路与遗留 helper 区别、验收 uncovered 不阻断、恢复阶段限制、缓存/进程执行边界。
- **官方资料支持**：候选框架功能和生命周期，来源链接在选型报告的具体段落旁。
- **工程推断/建议**：LangGraph 适配收益、工期、性能门槛、目标接口与操作日志。需要后续 PoC/评审，不是已实现或已测结果。
- **未验证**：真实模型成功率/Token 节省、框架运行性能、LangGraph 与本机依赖组合、Linux CI、强安全隔离、网络封锁、硬件性能 gate、任意恶意代码对抗。

## 7. 文档交付完整性

报告生成后检查 Markdown 内部文件链接、代码围栏配对、五份必需文档存在性，以及 `git diff --exit-code`。新增文件集中于 `docs/architecture-review-2026-10-24/`；原有未跟踪历史审计文档保留。业务代码和依赖没有 tracked diff。

