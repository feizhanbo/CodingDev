# 跨模块关系与系统级推演

## 五组不可混淆的职责

| 关系 | 协作方式 | 为什么不能简单合并 |
| --- | --- | --- |
| Checkpoint / Journal / manifest | manifest 选择兼容引擎，checkpoint 恢复控制位置，journal 判断副作用结果能否复用 | 控制状态、执行身份和外部效果属于不同持久化边界 |
| Decision / Registry / Observation / Context | 决策提出动作；Registry 验证派发；Observation 记录结果；Context 选择下轮证据 | 模型请求不等于执行事实；历史事实不等于全部发给模型的消息 |
| RunBudget / 模型 / 测试 / 进程 | 上层提供全局约束，下层用较短 deadline，取消等待资源退出 | 时间判断本身不能终止线程或子进程，必须有所有权和清理协议 |
| 文件修改 / Git / candidate / 验收 | 工具产生文件变化；候选物化以冻结清单导出差异；独立测试验证候选 | 工具成功不等于业务正确；普通 Git diff 不包含全部未跟踪变化 |
| ShopFlow Service / Repository / Session | Service 决定业务提交点，Repository flush，Session 管理事务 | 跨多个 Repository 的业务不变量要求一个事务边界 |

## 一次完整任务的代码阅读路线

CLI.run → application.factory.create_runtime → ApplicationRuntime.execute(RunRequest) → bootstrap.initialize_components → RuntimeLifecycle.run_outcome/run/_run → `_prepare` 冻结证据 → LangGraphAgentRunner._execute_loop → guard/context/decide → DeveloperAgent → LLMClient → AgentDecision → execute_tool（Journal）→ Registry → 工具 → observe_step → StateManager → 下一轮 ContextBuilder → finish → verify_step → TaskVerifier → materialize_candidate → independent suite → 结果持久化与终态发布 → RunOutcome。

评测入口在上述执行后继续 hidden suite，并区分 smoke/capability；它不把 Fake 的成功换算成模型能力。ShopFlow 是工具操作和测试加载的业务代码，运行它的订单 Service 不参与 DevPilot 的 SQLite checkpoint 事务。

## 系统级故障推演

| 故障 | 处理归属 | 面试时需要说出的剩余问题 |
| --- | --- | --- |
| 模型返回合法 finish，但未改文件 | Verifier diff_non_empty 失败，修复反馈 | 合法结构不等于合法业务结果 |
| patch 成功，记录结果前强杀 | Journal prepared，不确定 | 本地文件与回执非原子事务，保守拒绝 |
| 模型已响应但图状态未保存 | 模型 completed 回执可复用 | 回执未保存则可能重复请求并产生未知费用 |
| 测试进程挂住 | 局部/全局预算触发，Event 和进程树清理 | wait_for 返回可能晚于设定秒数 |
| 验收通过但最终持久化失败 | 终态发布/生命周期处理 | 不能只看内存 phase=completed 宣告交付 |
| 订单 commit 后 API 响应丢失 | 当前无下单请求幂等机制 | 重试可能创建重复订单，不是 rollback 能解决 |

## 统一设计思路

两个项目都把“是否允许状态变化”放在确定性边界：DevPilot 用预算、协议、工具和验收门禁；ShopFlow 用条件 SQL 和事务。但不能将文件回执类比成数据库事务的同等保证。数据库内部事务有统一提交边界，DevPilot 横跨文件、SQLite、子进程和远端模型，采用可检测、可拒绝的恢复策略。

“十倍规模”应拆开回答：任务数增加需要排队/并发隔离；单仓库变大需要分析清单扫描/复制/上下文；运行时间变长需要产物保留与恢复策略；订单写入增加需要数据库锁竞争与索引/分页实测。上述是未来研究方向，不是当前已经达到的容量结论。

## 对第一阶段的细化与修正记录

- 第一阶段“冻结测试/配置”是摘要说法：实际快照保存清单内全部文件，只有 protected 子集禁止修改。
- 工具 prepared 拒绝重放不能推广到模型请求：模型保留已用尝试并允许在余量内继续请求。
- Registry 注释 never raises 与实际配额异常/取消传播不符；以实现为准。
- “异常 rollback”只针对尚未提交事务；commit 后 refresh 或响应失败不能撤销已提交订单。
- phase 引导不是严格强制的先计划后编辑流程；字符压缩也不等于精确 token 预算。

## 下一阶段建议与本人待确认

第三阶段优先复盘订单事务改造、Graph 迁移和预算/恢复修复，逐个读取 Git diff 和对应失败测试，形成“问题→原因→选择→改动→验证”的故事。不要立即扩充通用八股题库。

仍需本人确认：负责哪些模块；哪些方案亲自比较过；哪次 Bug 亲自定位；项目实际使用者；真实模型运行样本是否保存；哪些代码和测试由协作或 AI 辅助完成。当前代码能证明机制存在，不能证明个人贡献比例、工作时长或生产效果。
