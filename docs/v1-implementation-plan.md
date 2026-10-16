# DevPilot V1 可信验证收口实施计划

制定日期：2026-09-12。依据：引用会话《项目分析与规划》、仓库详细设计文档、远程提交与当前工作区源码及现存验证产物。本文件是后续实施方案；列出的验收目标不代表已经完成。

## 1. 版本与现状

已执行 `git fetch origin`。远程为 https://github.com/feizhanbo/CodingDev.git，当前分支 main。HEAD 与 origin/main 均为 `1ee0adf0549a807e1b99705c027742c48d634292`，ahead/behind = 0/0，本次检查不需要再次拉取。已有执行记录记载从 ae96604 快进同步过九个提交。工作区有大量未提交修改，因此“提交已是远程最新”不等于“工作区内容与远程完全相同”。保留这些修改，后续先整合验收，避免重复实现。

| 范围 | 当前可核对事实 | 后续判断 |
|---|---|---|
| Runtime / Tools / Context / Trace | V1 核心研发闭环已存在 | 保留 Custom Runtime，聚焦可信交付 |
| 配置与打包 | 本地已有 Settings、Python 3.12、目标测试解释器、包内 eval 资源、wheel 检查脚本 | 重新验证最终组合和安装态，不能只沿用旧 wheel 结果 |
| 八项 Benchmark | 本地已有 manifest、起点补丁、参考修复、独立 fixtures、八项 hidden suites | 已有确定性证据，但需要最终代码版本与跨平台复验 |
| Benchmark 证据 | runs/benchmark-validation-01/summary.json：八项均负例 FAIL、参考修复 PASS、visible PASS | 证明题目和参考解有效，不证明模型能力 |
| 可信测试与评测状态 | 本地已有冻结基线、实际文件差异、独立 harness、四态结果、smoke/capability 区分 | 全量兼容性与对抗测试尚需收口 |
| 全量回归 | devpilot/runs/hardening-unit.log 当前可见多个 F，读取时尚无最终汇总 | 现阶段不得宣称全绿；先获取完整失败清单 |
| 指标 | MetricsCollector 有字段；LLM usage 在解析之后获取，decide 数据链仍需接通 | 不能把缺失 token 或 regression 当作 0 |
| 工作区安全 | copytree 仍只对 symlink 告警；pytest 使用宿主执行 | 文件副本不是强安全沙箱 |
| CI | 本地存在 Windows/Ubuntu 工作流草案 | 未核验远程运行成功 |

引用会话关于方向的判断仍成立：先完成 V1 Verification & Eval Hardening。其“只有五项 hidden tests”等细节对应远程基线，不能直接套用到已变动的本地工作区。现有 docs/v1-hardening-progress.md 的 TODO 状态也已落后于代码，需用新证据更新。

## 2. 目标和范围

目标是可靠回答：指定版本、题目起点、模型和配置下，Agent 是否完成任务，是否引入回归，消耗多少资源，以及失败发生在哪一层。

本阶段交付统一配置、可信基准与验证器、完整观测和可重复评测、受控本地执行的明确边界、双平台 CI、可复核的真实模型报告。

本阶段不扩展 LangGraph、多 Agent、Dashboard、GitHub Issue→PR 产品流程或持久恢复。容器级强隔离作为接入不可信仓库前的独立后续门槛；宿主进程加固不宣称具备容器边界。

## 3. 实施顺序与依赖

M0 整合基线 → M1 配置与资源验收 → M2 Benchmark 验收 → M3 可信验证收口 → M4 指标与重复评测 → M5 执行安全和 CI → M6 真实模型评测与发布证据。

M5 的执行器可以在 M3 接口稳定后提前开发；首次真实评测必须等待确定性门禁和执行边界通过。以下按一名开发者有效工作日粗估，总计约 13–20 日，模型调用与外部 CI 等待另计。已有实现可缩短时间，但不减少验收。

### M0：整合当前工作区（0.5–1 日，P0）

1. 保存 Git 状态、源码提交、工作区 diff 指纹与 Python/依赖版本；清点新增、移动、删除文件，特别是 evals 迁入包内的资源完整性。
2. 等当前全量测试结束，按生产缺陷、旧测试契约、环境依赖分类；逐项定位失败。更新旧 fake 测试以符合真实修复流程，不能削弱防篡改策略让测试通过。
3. 检查 Runner 初始化、快照失败和异常退出是否均留下结果与日志；修复状态或指标跨 run 泄漏。
4. 将后续改动按配置、基准、验证、指标、安全分成可审查提交；不把密钥、缓存和运行工作区纳入 Git。

验收：DevPilot 和 ShopFlow 全量测试、Ruff 通过；每个 skip/xfail 有原因；失败清单归零或作为明确不满足验收项记录，不能用旧报告代替。

### M1：配置、运行路径与安装态（0.5–1 日，P0）

涉及 settings.py、cli.py、runtime/base.py、tools/context.py、tools/test/run_tests.py、pyproject.toml、scripts/check_wheel.py。

- 固定参数优先级：显式 CLI > 环境变量 > .env > 默认值。run/eval/inspect/diff 使用同一配置来源。
- 验证 max_steps、max_test_retries、max_modified_files、max_patch_failures、test_timeout_seconds 都传递到实际执行点，并验证边界值。
- 用目标项目 Python 执行其测试；避免 DevPilot 虚拟环境碰巧包含业务依赖造成假通过。
- 全部日志、JUnit、trace、diff、结果落到配置的 runs_root；每次测试独立文件，不能覆盖上次失败证据。
- 重新构建 wheel，在源码目录外新建环境安装；验证 CLI、八项 YAML、hidden fixtures、manifest 与补丁哈希、fake smoke 均可用。

验收：配置覆盖、中文/空格路径、自定义 workspace/runs 目录、目标解释器和安装态运行均有证据；文档与 .env.example 一致，公开快照不含密钥。

### M2：八项基准可信性（1–2 日，P0）

涉及 devpilot/evals/benchmark.py、benchmark/manifest.json、issues/、hidden_tests/、shared/、scripts/build_benchmark.py。

为每题固定源码提交、初始文件哈希、起点补丁及测试版本。起点与参考修复仅由评测器准备；Agent 工作区不包含 hidden tests 和参考答案。更改题目行为必须升级 dataset_version。

| Issue | 业务验收重点 | 起点/验证注意事项 |
|---|---|---|
| DEV-001 | 状态过滤、非法状态、先过滤后分页、不传参数兼容 | 验证 API 返回内容，禁止占位断言 |
| DEV-002 | shipped/completed 不可取消，允许状态不回归 | 上游已具规则，使用专属缺陷起点 |
| DEV-003 | 负分页参数返回 400，正常边界稳定 | API 与 repository 行为一致 |
| DEV-004 | 百分比优惠上限、金额边界 | 校验最终业务金额 |
| DEV-005 | 冷 Session 查询数有界；1000 项 API 性能 | 固定注入查询放大缺陷，查询数和耗时分别报告；500ms 阈值注明机器环境 |
| DEV-006 | Email 去空白、小写、持久化一致 | 以实际模型赋值/存储入口为准，不凭空新增客户 API |
| DEV-007 | 禁止重复支付，失败不改变既有状态 | 上游已具规则，专属缺陷起点；不夸大并发幂等能力 |
| DEV-008 | updated_at/paid_at/cancelled_at、API 兼容、SQLite 迁移 | python -m app.db.migrate 可重复，旧行保留；历史未知审计字段可空 |

验收：每题缺陷起点出现业务断言失败，不能因缺依赖/fixture 通过负例检查；参考修复后 visible 与 hidden 全过且无意外 skip。八题完整完成后总报告才允许 passed=true。性能结果独立记录，避免共享 CI 抖动掩盖功能结果。

### M3：验证器和评测结果收口（2–3 日，P0）

涉及 verification/evidence.py、verifier.py、apply_patch.py、create_file.py、evals/runner.py。

- 冻结运行前可信测试与配置；禁止 Agent 改删已有测试、conftest、pytest/项目配置；允许新增普通回归测试。
- 写工具检查与最终全文件校验同时存在。根据文件系统差异计算变更范围，包含未跟踪文件与删除，不依赖模型自报或只有 git diff HEAD。
- 在 Agent 工作区外运行冻结 visible suite 和 hidden suite；固定配置、fixtures、导入入口，防止候选 conftest 改收集规则。
- 依据 JUnit 区分断言失败、收集/执行错误、零收集、全部跳过；缺失及明显占位 hidden suite 不能判 PASS。AST 检查只作辅助，不作为强安全保证。
- final.diff 可恢复所有允许交付的修改；异常路径仍保存 policy 原因与尽可能完整证据。
- fake 使用独立小型仓库，实际先失败再修复；只统计为 smoke。

结果协议：PASS=可信验证完整通过；FAIL=有效执行得到不满足要求的结果；NOT_EVALUATED=缺少有效评测依据；ERROR=运行或评测基础设施异常。task_success 对未知结果为 null。报告同时列四态数量和覆盖率，禁止将基础设施错误伪装成模型成功。

验收：删除测试、覆盖配置、增加 assert True、绕过路径、未跟踪文件、隐藏 fixture 缺失、全部 skip、collection error 等用例均被正确处理；smoke 不进入能力成功率。

### M4：完整指标与重复运行（3–4 日，P1）

涉及 llm/base.py、llm/openai.py、agents/developer.py、runtime/custom/runner.py、tracing/、evals/runner.py、cli.py。

1. 在 LLM 请求层记录 request_id、attempt、模型、单次延迟、input/output/total tokens、解析状态和错误类别；在 JSON 解析前保存 usage。明确 SDK 自动重试计数策略，避免漏记或双计。
2. run 开始初始化所有计数、LoopGuard 和缓存生命周期；区分 Agent 测试调用、Verifier 测试、Eval 测试及修复次数。
3. 记录 total_steps，平均值只在聚合层计算。未知 usage、价格或基线统计为 null，记录原因；金额仅在提供版本化价格表时计算。
4. 先执行可信起点 visible suite，记录原先通过的 node IDs。回归率分母为原先通过节点，分子为修复后不再通过节点；原先已失败的任务测试不能算新回归。零分母、收集不完整或基础设施异常不能报告零回归。
5. 增加 repeat 和批次标识：建议接口 eval --all --repeat 3；每次独立工作区，每题各三次，失败不中断其他题的证据保存。恢复批次必须显式记录，不覆盖或择优替换失败。
6. 保存 schema_version、dataset/prompt 版本、源码 commit、dirty diff hash、模型配置、Python/依赖锁哈希、操作系统、开始时间与运行状态。
7. 离线从 artifacts 重建 JSON/Markdown 汇总；旧产物缺字段标注 legacy/unknown，不能与新协议无提示混算。

验收：成功、API 异常、重试和解析失败均可对账；连续两次 run 无状态污染；重复评测调度数量正确；离线重建与在线汇总一致。小样本报告原始计数，不宣称统计显著提升。

### M5：受控执行与双平台 CI（3–5 日，P0/P1）

涉及 workspace/sandbox.py、运行子进程的公共执行器、tools/test/run_tests.py、evals/benchmark.py、.github/workflows/ci.yml、dev.ps1。

- 复制前拒绝或显式处理 symlink/junction/reparse point；防止跟随路径复制仓库外文件。过滤 .env、凭据及不应进入候选工作区的运行产物。
- 测试进程用环境白名单，清除模型 API 凭据、用户插件自动加载和非必要 Python 路径；显式选择配置与允许参数。
- POSIX 使用进程组，Windows 使用 Job Object 管理整个进程树；超时后清理子孙进程，保留部分输出，标记 timeout。单独 kill pytest 主进程不算验收。
- network_access=false 必须由执行后端落实；若本地后端不能保证，启动时明确拒绝该组合。受控本地执行需显式 network_access=true，并在产物记录“无网络隔离”。
- 将任意不可信仓库执行留在强隔离后端交付之后；上述保护不能阻止所有同用户宿主访问。
- CI 在 Ubuntu/Windows Python 3.12 安装 frozen locks，运行双方 Ruff/pytest、deterministic smoke、八题基准自证与源码外 wheel 检查；失败也上传日志。
- PowerShell 任一步失败向外传播非零退出码；处理中文路径与 UTF-8 日志。

验收：环境探针读不到传入父进程的测试密钥；路径逃逸被拒绝；超时后子进程不存活；不支持的网络隔离请求失败而非静默降级；最终提交两个系统的 GitHub Actions 均实际通过，并记录运行链接。

### M6：真实模型基准与交付（2–4 日，P1）

前提：M0–M5 确定性门禁完成；有效模型/endpoint/凭据已在本地配置，凭据不写入报告。若凭据缺失，记录外部依赖，不能用 fake 补足真实评测。

- 固定一个模型、temperature、预算、prompt、代码与数据集版本，执行 8 题 × 3 次独立运行，共 24 次计划样本。
- 首次可先跑 DEV-001 一次验证连接和产物，但先声明它是预检还是正式样本，防止事后选择通过结果。
- 展示每次四态结果、visible/hidden、回归、steps/retries、token/延迟、变更范围、失败阶段及 artifact 路径。保留全部失败。
- 建议能力门槛：DEV-001 达到 3/3；DEV-002–005 中至少三题达到 2/3；DEV-006–008 如实报告。此为把设计文档稳定性要求具体化的建议，不是已有能力结论。
- 工程通过与模型达标分别给结论。模型未达标时按探索、规划、修改、修复或预算分类，用下一版 prompt/context 做新批次，禁止事后修改同版本题目评分。

验收：24 次都有终态与可追溯证据；报告可离线重建；公开配置脱敏；README 的每条能力描述有对应测试或真实运行证据。

## 4. 提交拆分与风险控制

建议依次提交：配置/资源；基准与参考解；可信验证及 smoke；指标协议；重复调度/报告；执行加固；CI/文档；真实评测报告。每个提交附针对性测试，接口跨提交时保持主分支可运行。现存大工作区先审阅再拆分，避免将未验收代码直接作为发布版。

主要风险：旧测试依赖可修改测试的假流程；评测代码与 Runtime 强耦合；宿主执行边界被误认为安全隔离；性能机器差异；真实 API 成本和服务故障；旧结果混算。分别以真实 smoke fixtures、稳定组合接口、明确后端能力、记录平台/分离性能指标、批次预算及四态协议、版本化读取器处理。

## 5. 最终交付清单

- 可安装 wheel 与统一配置说明。
- 八题版本化基准、负例/参考修复验证报告。
- 不可被普通工具改写的可信测试基线、完整 diff 与四态评测。
- 请求级指标、重复批次 manifest、离线报告与 legacy 兼容说明。
- 受控执行边界说明、进程树/环境/路径测试。
- 双平台成功 CI 链接与完整本地测试报告。
- 24 次真实结果及工程/能力两份结论。

下一步具体动作：先完成 M0 的全量失败定位与工作区整合，不再新增框架或功能面。
