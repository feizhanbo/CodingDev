# 当前自研 Runtime 版本完成度与展示差距

评估基线：2026-11-16，HEAD `549e7c9`（回退 LangGraph/LangChain 迁移）。本报告评估当前源码，不使用迁移版测试结果证明本版本质量。未修改业务代码。

## 总体判断

当前是具备完整执行闭环的本地单 Agent 工程实验平台。V1 核心功能已有实现，展示产品尚未完成，当前真实模型能力与稳定性需要另行验收。自研 Runtime 是项目技术特点，不需要为了求职重新引入框架。

## 功能盘点

| 功能 | 当前实现和证据 | 完成边界 |
| --- | --- | --- |
| 任务输入 | cli.py 的 load_issue，结构化任务字段校验 | 以 YAML 为入口；不是网页聊天或 GitHub Issue 自动接入 |
| 自研执行循环 | runtime/custom/runner.py；state_manager.py | 单 Agent，非多 Agent 或分布式调度 |
| 计划与阶段 | 结构化决策、计划更新、状态推进 | 实际计划质量取决于模型，不能只凭协议评价质量 |
| 上下文 | runtime/custom/context.py，任务、状态、观察、失败信息与压缩 | 字符预算，不是精确 token 裁剪；无向量 RAG/长期记忆 |
| 模型接入 | llm/openai.py，OpenAI 兼容客户端、JSON 输出及校验 | 工具描述进入上下文、模型输出结构化决策；不是供应商原生 Tool Calling 协议 |
| 工具系统 | cli.py 注册 8 个工具：列文件、搜索、读取、补丁、新建、测试、Diff、Status | 受控能力集，无通用 Shell 工具 |
| 代码修改 | tools/code/apply_patch.py，Git 补丁检查与应用 | README 三级补丁后备描述与当前实现不一致 |
| 测试及自我修复 | test.run、失败解析和反馈进入下一轮 | 确定性修复闭环已复测；真实模型修复能力未本轮验收 |
| 最终验证 | verification/verifier.py，独立测试、修改范围、禁止路径等检查 | coverage_for 对未绑定自然语言验收条件标记 uncovered；completed 不等于全部需求已证明 |
| 工作区和限制 | workspace、security、path_guard、RuntimeConfig | 本地目录隔离及路径策略，不是容器/操作系统级不可信代码隔离 |
| 预算治理 | 步数、请求数、重试、执行时限、输出及磁盘额度 | 不等于多租户配额、CPU/内存硬隔离 |
| 持久化和恢复 | checkpoint.json、RunLock、custom/recovery.py | 仅兼容的 ready/llm_inflight 普通运行可恢复；拒绝工具/验证中断、终态及评测恢复；校验环境与工作区 |
| 可观测与交付 | Rich 进度、state/result、JSONL Trace、模型请求记录、final.diff、inspect/diff | 文件与命令行层；无独立 Web 看板或集中式可观测平台 |
| 评测 | evals/runner.py；8 个基准任务与独立隐藏测试 | Fake smoke 不跑隐藏验收且不计能力成功率；基准参考补丁通过不等于模型成功 |
| 业务载体 | ShopFlow 的 FastAPI、Service、Repository、模型与数据库代码 | 用作 Agent 修改与验证对象，不是商业生产履历 |

## 本轮运行证据

针对当前版本执行计划流、状态管理、循环守卫、评测真实性、框架独立性五组测试：`tests/test_planning_flow.py tests/runtime/test_state_manager.py tests/runtime/test_loop_guard.py tests/test_eval_truthfulness.py tests/test_framework_independence.py`，结果 **72 passed in 93.15s**。这是定向回归，不是全量回归，也不证明真实模型任务成功率。

执行 `python -m devpilot.cli run devpilot/evals/issues/DEV-001.yaml --fake`，退出码 0，run_id 为 `run_22f0d706`。7 步完成：首次测试 2 failed，随后修复 calculator.py、新增 tests/test_addition_edges.py，最终 3 passed，Verifier 通过。产物位于 devpilot/runs/run_22f0d706。

该运行虽然使用 DEV-001 标题，Fake 实际执行的是内置计算器样例，不能描述为订单状态筛选完成。输出明确显示验收覆盖 1/4 verified、3 uncovered。这是流程验收证据，不是真实模型业务能力证据。

## 对照求职展示期望

| 期望 | 差距 | 建议验收标准 |
| --- | --- | --- |
| 真实模型完成业务任务 | 有接入实现，缺本版本经核验的端到端演示证据 | 使用真实模型完成至少一个功能和一个 Bug；保存模型配置、输入、Trace、Diff、独立测试与用量；明确失败样本 |
| 可视化展示 | 当前主要是终端输出和文件 | 页面选择任务、启动运行、显示阶段/工具日志/测试/Diff/历史记录，数据来自真实 Runtime；回放明确标注 |
| 功能演示 | 已验证机制，业务演示尚未闭合 | 展示需求、执行、验证、修改前后接口行为；有可复现环境和演示说明 |
| 稳定性证明 | 历史测试不能代替当前版本质量或模型效果 | 当前版本回归；固定任务集记录尝试次数、成功率、耗时与失败原因，避免单次成功外推 |
| 详细讲解实现过程 | 有足够技术内容，但部分材料对应迁移版 | 以当前提交重写架构与讲稿，挑选验证器、失败修复、恢复边界三条实现链，说明本人实际贡献 |
| 完整验收 | 多数自然语言条件未绑定确定性检查 | 为核心演示任务逐条绑定独立测试/业务检查，UI 同时展示未覆盖条件 |
| 清晰项目说明 | README 部分实现描述过期；面试目录描述迁移版 | 统一版本、术语和证据口径，区分已实现、已复测、待验证与未来计划 |

优先顺序：真实模型案例与验收证据 → 最小 Web 展示 → 业务效果演示与录像 → 当前版本说明、讲解和重复评测。无需先增加多 Agent、RAG 或框架迁移。

原 V1 设计明确排除自动提交/推送/PR、外部 Issue API、长期记忆、多 Agent、任意 Shell 和生产部署；这些不应被算成 V1 未完成项。Web 展示是对本次求职展示目标的补充需求。
