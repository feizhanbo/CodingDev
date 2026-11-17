# 工程问题与解决过程复盘

以下 P01–P08 是复盘编号。历史修改不自动代表真实线上事故；问题如何被发现、谁提出方案、是否亲自排查均待本人确认。

## P01：验收依赖候选工作区，证据不够独立

- **背景/表现**：研发 Agent 能修改目标仓库，验证若继续通过同一 test.run 获取通过结果，测试配置与被测代码的信任边界不清。
- **历史与原因 H**：`4a8a778` 的 `verification/verifier.py` diff 显示原 verify 先调用 `_check_visible_tests(workspace_path, ..., registry)`，再检查 diff/禁止文件/数量；新实现先要求已绑定 trusted baseline，新增 evidence.py。根因是执行结果与独立验收证据没有充分分离，不是“原项目完全没有 Verifier”。
- **方案选择 I**：与继续增强提示词相比，固定测试与候选复制可以在模型外强制执行；代价是复制与测试开销。
- **实施 H/C**：快照保存文件摘要和保护集；check_integrity 检查受保护文件，materialize_candidate 基于实际清单产生 diff；可见与新增测试分开执行。当前 suite 位于 `testing/suite.py`，不要沿用历史 import 路径。
- **效果证据 C**：`tests/verification/test_evidence.py` 的删除基线测试、未跟踪文件、新增简单测试掩盖旧失败等断言验证了相关边界；不证明所有需求完成。
- **局限/经验**：测试可证明的范围有限，coverage_for 会标记 uncovered；工程价值在定义可信成功口径，而不是宣称模型不会出错。

## P02：库存和订单不在同一事务

- **背景/表现**：一个请求跨商品、订单与明细，任一步失败都应维持库存与订单一致。
- **历史 H**：`34e6e7e` 中旧 create_order 先查询库存，调用订单 Repository.create，再逐项 update_stock；Repository 各自 commit。新版本 Repository 改 flush，Service 用 try/commit/except rollback。
- **原因分析**：拆开的提交点无法回滚已提交部分；Python 读库存后写回与条件更新的并发语义不同；重复商品还需按总需求判断。
- **实施 H/C**：合并数量、条件库存 UPDATE、按状态条件迁移支付/取消，取消仅 changed=True 时回补；同一 Session 提交。
- **选择 I**：单库不变量优先放进数据库语句与事务，额外 Redis 锁不会替代提交原子性。没有证据证明当时实际试过 Redis。
- **效果 C**：`test_failure_rolls_back_everything` 在第二商品、明细 flush 后、commit 前注入失败，断言库存保持原值且订单/明细为零；`test_cancellation_restores_stock_once` 连续取消后库存只恢复一次。
- **局限/经验**：提交成功后响应失败仍缺下单请求幂等。并发测试 `test_concurrent_payment_and_cancellation` 实际先做两个并发支付，再做两个并发取消，并非一个支付与一个取消混跑；不能从名称夸大覆盖。

## P03：图恢复无法独自判定文件副作用

- **背景/表现**：图节点重执行可能重复已执行但尚未 checkpoint 的工具操作。
- **历史 H/C**：`41c4ea5` 引入图运行时和 operations.py；当前 Journal 记录 prepared/completed、参数摘要、后置工作区摘要和结果摘要。旧 custom 恢复对于 tool_inflight/verifier_inflight 是保守拒绝；不能说旧版本会无条件重放。
- **原因**：SQLite 图状态和普通文件写入无法共同提交；副作用成功与回执写成功也有窗口。
- **方案/实施**：图执行工具前 begin，执行后 complete；恢复已完成且匹配结果，否则 ManualRecoveryRequired。模型请求使用另外的对账路径，保留次数及未知用量，不能照搬工具拒绝策略。
- **效果 C**：`test_operation_journal.py` 覆盖 prepared 不重放、参数变化拒绝、落盘失败保留 prepared；`test_graph_resume.py:test_resume_tool_crash_window` 区分 completed 是否保存。
- **局限/经验**：保守失败降低可用性但避免不安全重做；它不是 2PC 或 exactly-once。远端副作用需提供方幂等/查询协议。

## P04：超时返回不等于测试进程结束

- **背景/原因**：模型、测试、Git 命令都有生命周期，取消等待线程不会自动杀掉进程树。
- **历史 H**：`f7ba445` 新增 processes.py，含 Windows Job、受控 launcher、输出限制、取消协作；本轮读取新增文件相关片段，不把所有后续能力都归于这个提交。`41c4ea5` 的 ApplyPatch diff 将自行 create_subprocess_exec/communicate 改为共享 capture_process_async。
- **实施 C**：当前 Event 通知 worker，shield 后等待清理；run_process 管理父子进程、stdout/stderr 额度与句柄；RunBudget 管理跨恢复全局时间与累计验证时间。
- **选择 I**：统一进程执行器减少各工具遗漏超时和清理的风险；平台专用 Job 与线程协调增加复杂度。
- **效果 C**：`test_processes.py` 有取消等待清理、父进程结束后子进程停止、输出限额、Job 绑定失败不启动候选等测试；未据此声称任意恶意程序受控。
- **局限/经验**：协作取消可能延迟返回，无 CPU/内存硬限制；应明确谁拥有资源以及何时交还控制权。

## P05：恢复编码和运行 ID 冲突破坏证据

- **历史 H**：`05d26dc` 将 checkpoint.read_text() 改为显式 UTF-8；新 run 从直接生成短 ID 改为循环尝试目录独占创建，冲突则换 ID。
- **表现/原因**：默认 locale 可能不匹配 UTF-8 JSON；随机 ID 概率低不等于可忽略旧产物覆盖。
- **实施 C**：当前共享 lifecycle 保留显式编码和 exist_ok=False 创建；原子目录创建使“检查不存在”和“占用名称”不只依赖前置 exists。
- **证据 C**：`test_chinese_resume_with_utf8_mode_disabled` 另启进程关闭 UTF-8 模式验证中文任务；`test_new_run_id_collision_preserves_existing_evidence` 注入一次 UUID 碰撞并断言旧 result 内容未变。
- **选择/局限/经验**：小改动无需增加数据库，保留既有磁盘布局；不代表任意损坏文件都能恢复。持久化协议必须明确编码、身份与不覆盖规则。

## P06：软压缩后仍可能超上下文预算

- **历史 H**：`41b027b` 把固定 30000 改为 config.max_context_chars，新增 `_enforce_limit`、reserved_chars 和硬失败；验收反馈由只认 verification/detail 改为也识别 verification_failed/message，并显式加入 verification_report。
- **原因/表现**：降低近期观察数量未必让完整请求足够短；反馈字段名不对应会丢诊断细节。
- **实施 C**：裁剪可删除观察的投影，保护当前失败和守卫反馈；固定内容仍过大则停止；最终协议再验证消息预算。
- **效果**：当前代码可保证过限不直接继续发请求，测试入口 `test_context_compression.py`、`runtime/test_context_feedback.py`；不证明 token 精确计数或模型修复率提升。
- **选择/局限/经验**：规则压缩可重复且无额外模型成本，但有损；接口字段和真实反馈比不断堆提示词更值得先核查。

## P07：清理目录校验了错误的路径对象

- **历史 H**：`dccd2ba` 将 `workspace_dir.parent.resolve()` 改为 `workspace_dir.resolve().parent`。前者先取父路径，不能等价证明规范化后的删除目标仍属于允许根目录。
- **实施/证据 C**：当前 SandboxWorkspace.destroy 仍验证最终目标；同提交新增 `test_destroy_rejects_resolved_targets_outside_workspace`，参数包括 `..`、`.`、`../outside`、`nested/../../outside`，mock rmtree 并断言没有调用。
- **选择/效果**：修正边界表达式，保留既有接口；证明这些危险输入被拒绝，不是已发生真实误删的证据。
- **局限/经验**：同机并发替换路径仍涉及检查与使用竞态；安全判断应针对最终操作对象，而非看起来相关的父目录。

## P08：迁移框架时业务语义与成本必须一起验收

- **背景 D**：2026-10-24 选型文档要求保留自有工具权限、预算、验收和离线测试，明确未运行候选框架 PoC。
- **实施 H/C**：`41c4ea5` 新增应用边界、图、共享生命周期和回执；默认改 langgraph/langchain，旧入口保留。图不是将整个 custom.run 包成一个节点。
- **验证 C/D**：当前 `test_graph_business_contracts.py` 更换构建边界复用业务断言；最终验收文档记录 Windows 回归、旧路由和包安装验证，但本轮未重跑。
- **取舍 D**：performance-decision.md 明确接受持久化额外成本；不是性能优化结论。测量为 Fake 驱动真实本地操作，不外推真实模型或并发容量。
- **局限/经验**：新框架带来 checkpoint 序列化、回执对账、版本身份、终态发布等新复杂度；迁移成功应以语义保持和可接受成本衡量。
