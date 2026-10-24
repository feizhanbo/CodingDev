# 分阶段实施与验证计划

状态：方案评审稿；本轮未执行以下改造。路线 B 保留 Custom 与 LangGraph 并行，但业务服务只有一份。总估算 28–45 人日，包含工程治理，不包含收费模型评估与生产隔离平台建设；风险按代码理解后的估计，阶段完成后重新估算。

## 阶段任务与出口

所有代码路径共同前缀为 `devpilot/devpilot/`；测试前缀为 `devpilot/tests/`。

|阶段/依赖/工作量|目标及增改删|测试方法与完成判据|风险与回滚|
|---|---|---|---|
|P0 基线与契约；无依赖；2–3 人日|冻结当前源/benchmark manifest/依赖/测试结果；新增运行契约矩阵及故障样本；不删代码|重跑本报告失败项并归因；记录所有已知失败，不能把红基线当新运行器通过；Fake trace、预算、结果格式可重现|低；仅测试/文档可独立撤销|
|P1 确定性治理；P0；4–7 人日|改 context.py、state_manager.py、runner.py、verifier.py、tools 子进程调用；统一验收 observation、修复 phase、强制生产 verifier、硬上下文 admission、取消清理；补 alias 冲突规则；不换框架|新增早期 finish 被拒后的修复、验收反馈字段、超长任务/计划、取消 Git/rg 无残留、恢复预算不重置用例；现有文件保护/验收/预算测试不退化|中；按规则分提交，回滚单项；不得因新图需要而放宽保护。OS 执行隔离单列后续平台工作|
|P2 公共服务与接口；P1；4–6 人日|新增 composition.py、runtime/contracts.py、runtime/services.py、testing/suites.py；瘦身 cli.py、evals/runner.py、verifier.py；提取 reducer/Policy；旧入口做代理；迁走重复 suite 函数|不导入 runtime.custom 的替代 RunnerPort stub 可完成 EvalRunner 路径；pytest/Fake 的调用序列、终态、diff、请求/观察计数一致；不只做 import 测试|中；保持旧工厂包装，逐层恢复委托；一次只改一条依赖方向|
|P3 无自动副作用恢复的图试点；P2；5–8 人日|新增 runtime/langgraph/{runner,graph,nodes}.py 与可选依赖/锁版本；新增 `--runtime custom|langgraph`，默认 custom；只用共享服务|同一 Fake 脚本、相同 task/初始 hash，在两个独立工作区执行；结果/工具标准名/验收判定/预算完全一致；测试失败→修复→拒绝 finish→再次验收均覆盖|中；开关切 custom，只影响新 run；保留新图产物，不把新 checkpoint 交给旧 runtime|
|P4 持久恢复与 HITL；P3；6–10 人日|新增 checkpoint adapter、operation journal、resume router、approval record；保留 recovery.py 旧格式读取；扩展状态 waiting/needs_reconciliation；不删除旧 checkpoint|在请求前后、文件写入前后、journal 提交前后、验收前后强制中断；检查无重复 patch、无预算刷新、漂移拒绝、锁互斥、审批 hash 校验；不确定结果必须停而非自动成功|高；关闭新恢复入口，保留数据；必要时人工导出 patch并新 run，不回放 inflight|
|P5 配对评估与默认切换；P4；4–6 人日|参数化已有测试与 benchmark；评估器消费同一 candidate_ref；为新 run 灰度默认；清除确认未使用的旧 helper/常量|下述替换门槛全部满足才切默认；两个 runtime 共用的业务规则不得出现复制版本；真实能力验证须另行授权模型调用|中高；立即将新任务默认切 custom；进行中的 graph run 按版本固定继续/停止，不热切到旧 runtime|
|P6 收敛；P5 稳定观察后；3–5 人日|删除旧重复调度、旧状态推进路径；保留 legacy checkpoint 只读导出及旧版本运行入口到保留期结束；更新依赖/文档|一轮完整离线回归与恢复矩阵；核对历史产物读取；独立验收与 hidden 资源保持完整|中；通过版本标签/锁文件恢复旧发行版；不做有损 checkpoint 降级|

P0 是首先实施的阶段。P1/P2 即使最终选择 A 也有独立价值。若 P3 增加了明显重复维护或无法保持语义，停止引入图而保留公共服务改造，不继续投入 P4。

## 复用现有测试与差分基线

1. 领域/工具：`domain/`、`tools/`、`workspace/`、`test_file_security.py`、`test_processes.py` 不依赖框架；新增后端应运行相同契约套件。
2. 编排：参数化 `runtime/test_runner.py`、`test_repair_loop.py`、`test_request_budget.py`、`test_loop_guard.py` 和 `test_context_feedback.py`。不要为 graph 复制测试期待；业务期望为唯一 oracle。
3. 证据与恢复：复用 `verification/`、`test_hidden_test_isolation.py`、`test_persistence.py`、`runtime/test_recovery.py`；增加真实崩溃窗口和旧产物兼容测试。Fake 不能证明 OS 隔离，后者需要独立执行后端测试。
4. CLI：`test_cli_commands.py`、`test_cli_e2e.py`，保留 YAML、退出码、八工具名、JSON schema；增加 runtime selector 和按记录 runtime 路由 resume。
5. Benchmark：保留 DEV-001…008、manifest、缺陷补丁和 reference；先证明负例确实失败、参考修复通过 visible+hidden。performance 测试单列硬件和环境，不能合入未声明的成功率。

本轮禁止收费模型，故只形成离线验证计划和当前证据。后续真实 A/B 需使用同一模型版本/provider 参数、同一任务与 starting_tree、预算、测试解释器、资源限额；每个 runtime 使用独立工作区，运行顺序交替，避免缓存和环境顺序偏差。不共享可变 Runner 实例。

## 指标定义与替换门槛

|指标|比较方式与建议门槛（待评审确认）|
|---|---|
|正确性|离线确定性脚本的终态、规范化工具序列、candidate diff、验收结论必须一致；修复既有缺陷时显式更新单独的契约版本|
|保护不变量|冻结测试不可改、敏感文件不可读、未知证据不得 PASS、预算不可刷新、未确认副作用不得重放：零回归|
|恢复可靠性|每类中断窗口至少重复 10 次，无重复写、无丢失终态；不确定窗口允许显式 needs_reconciliation，不得伪造恢复成功|
|成本|Fake 请求次数严格一致，已知/未知 tokens 口径一致；真实费用需输入输出 usage 与定价版本，不能拿 token_cost 空字段代替|
|性能|同机重复离线运行至少 20 次，比较中位数与 p95；建议无模型开销增幅 <=15%，否则分析 checkpoint/hash 开销；这不是已测得结果|
|能力成功率|能力评测单列 PASS/FAIL/ERROR/NOT_EVALUATED。报告总任务数、已评估率与 PASS/(PASS+FAIL)，不能通过剔除 ERROR 美化结果。八题样本太小，不据单轮认定显著提升|
|真实模型非劣性|经授权后按题配对至少 5 轮，汇报差值与置信区间；先约定可接受下降界限（建议 5 个百分点），证据不足则继续保留 custom 默认|
|可维护性|预算、工具执行、验收、结果构造只有一个共享实现；两套 runtime 仅留调度适配与恢复格式差异|

## 兼容与回滚细则

在 RunManifest 保存 runtime_kind、schema/graph version、package lock hash、模型身份和 baseline hash。旧运行继续由旧代码恢复；新图运行按新 graph version 处理。CLI resume 应读 manifest 再选择对应工厂，不靠当前默认 runtime 推断。现有 JSON 产物作为兼容投影持续输出，新字段不能改变旧键语义。

禁止把升级后的 checkpoint 直接覆写旧 checkpoint.json。发布回滚只改变新任务的入口默认和依赖版本；数据保留、版本路由与操作日志一起回滚规划。若新运行器产物需导入旧运行器，应作为显式人工检查后的新任务/patch输入，不能冒称原 run 无缝续跑。

生产级不可信代码隔离需要单独预算与设计评审：执行身份、挂载、网络、CPU/内存/进程数、测试日志及产物可信链。它不是 LangGraph PoC 成功就自动完成的阶段。本轮结论仅到方案评审，不部署、不改业务代码。
