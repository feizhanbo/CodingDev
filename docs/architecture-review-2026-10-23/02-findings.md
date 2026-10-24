# 架构问题与重构必要性

基线及证据口径同 `01-current-architecture.md`。严重度 P1 表示替换或扩展前优先处理，P2 表示可计划治理；没有声称下面静态发现都经过攻击性复现。框架不能替代确定性验收和执行隔离。

|编号/优先级|实际表现 → 根因|影响范围|是否需要框架 / 推荐处理|
|---|---|---|---|
|F01 P1|SandboxWorkspace 是目录副本；pytest 仍以宿主身份执行，network_access 仅配置 → 没有 OS 边界|不可信代码可以绕过工具路径检查；隐藏测试也只是对 Agent 工具不可见|不需要框架；新增独立 ExecutionBackend，受控用户/容器或 VM、网络策略、资源上限、只读可信挂载。当前只能定位为可信本地执行|
|F02 P1|search_code 逐文件 rg+communicate；apply_patch/git helper 使用原生子进程，无统一取消清理 → 测试进程治理未复用至其他工具|总 asyncio timeout 不保证底层进程停止；patch 取消后回写和仍存活 Git 可能竞争；输出先完整载入|工程问题；统一受管 ProcessService，终止并等待进程后回滚；设输入/输出与单工具上限。不能给所有工具自动重试|
|F03 P1|ContextBuilder 压缩后不复核长度，任务/计划完整保留、旧摘要持续增长 → 字符阈值仅触发策略|模型上下文溢出、费用上升；本轮 40,000 字符任务产生 44,298 字符上下文|不需要框架；ContextPolicy 做 token 估算与硬 admission；过大任务应显式拒绝或引用外部内容，不能静默删验收条件|
|F04 P1|runner 写 verification_failed，formatter 识别 verification 且读 detail，verifier 实际写 message；拒绝分支不设置 repair_required → 反馈协议和状态散落|验收失败落入通用 JSON 截断，修复提示不完整；understanding 到 implementing 转换失败被 suppress，保留旧阶段|先业务修复；统一 VerificationObservation 与 reducer，显式定义拒绝边，不吞状态异常；LangGraph 可表达分支但不能自动修字段契约|
|F05 P1|TaskVerifier 只覆盖冻结测试/变更规则/新增测试关键词；verifier=None 能直接完成 → 完成语义可绕过，任意验收描述没有执行断言|扩展调用方可能得到未验收 completed；不应夸大真实任务正确性|确定性业务规则；生产 Runner 必须注入 verifier；显式未验收状态；验收条目→检查证据矩阵，缺证据不得称全部满足|
|F06 P2|EvalRunner 改写 sandbox/purpose 并读取 verifier.last_results、deadline、metrics、state.json；Protocol 没声明全部需求 → 隐式鸭子类型接口|新 runtime 需复制内部属性；导入独立测试不能证明替换兼容|不依赖框架；用 RunRequest/RunEnvelope 和 ArtifactStore；factory 接受完整上下文，返回结果含证据引用|
|F07 P2|checkpoint 拒绝工具/验收执行中恢复，全目录含 .git 重复哈希；identity 哈希整包源码 → 保守恢复代价大且升级不能续跑|长任务中断需人工检查；大仓库每步磁盘开销；不是“完全没有恢复”|框架适合管理节点持久化与 interrupt；仍需操作 journal、内容 hash、兼容版本、恢复审计与 RunLock|
|F08 P2|_run 集中预算、模型重试、工具、状态、事件、验收和保存；实例 fields 在新 run reset → 单实例不可安全并发|增加 Agent/HITL 后分支增长、状态污染风险|先抽取每次运行 Session 与纯 reducer，再部分迁移框架；单 run 单写者，禁止共享可变 runner 并发|
|F09 P2|phase 根据工具/步数启发式前移，step 是 observation 数；测试与验收共用 retry_count|日志阶段与实际动作不总一致；迁移容易改变预算、重试语义|框架表达调度边；业务定义业务阶段/执行节点/attempt 三个独立概念；第一阶段保持旧计数兼容|
|F10 P2|请求数/单次 max_tokens/墙钟已有限额，但无总 token 或金额上限；准备与同步 copy/hash/git 不可被 asyncio 强制打断|大型仓库准备时间不受 max_run_seconds 覆盖；名为运行 timeout 并非全生命周期硬限时|工程治理；预算分 preparation/execution/evaluation，未知 token 保守记账；SDK/框架/业务只允许一层请求重试|
|F11 P2|save_artifact 对诊断文件豁免配额；TraceWriter 直接 append；恢复完整清单较大|预算是 admission 控制，不是物理磁盘硬限额；失败诊断仍可能增长|独立存储策略：预留有限诊断空间、统一写入/压缩/保留规则、内容寻址；不能简单移除失败诊断保障|
|F12 P2|隐藏测试使用 sandbox 当前路径，visible 使用 materialize_candidate 副本；verifier 依赖 evals.benchmark 执行器|证据输入不统一；verification→evals 的依赖方向反转，评估代码包含通用执行基础设施|把 parse_junit/run_independent_suite 提到 testing/，隐藏测试绑定已验收 candidate hash；保留评估自己的测试选择和判定|
|F13 P2|工具注册只拒绝相同原名，别名采用首个下划线转点；runner 部分仍有双名分支|当前八工具已归一，但未来扩展可能发生 alias 与正式名碰撞|业务层显式 alias 表、注册时冲突检测；迁移前后相同标准工具名，不引入第二次归一|

F04 的具体证据是 `runtime/custom/runner.py` 验收拒绝分支、`runtime/custom/context.py:_format_observation_data` 和 `state_manager.py:_ALLOWED_TRANSITIONS`。本轮只构造状态调用验证了 understanding→implementing 被拒绝，没有将该探针误称为完整端到端故障复现。F02 是静态取消路径风险，未在用户机器上制造残留进程。

## 旧问题复核

|旧问题描述|当前结论|
|---|---|
|失败模型请求不占预算|已改为 dispatch 前 request_count++；SDK retries=0；仍需未来框架保持同一记账边界|
|搜索绕过敏感文件限制|rg 与 fallback 均先过滤；剩余是 OS 隔离与资源治理，不应把已修漏洞重复列为现存|
|别名绕过统计与修复|决策执行前 canonical_name；现有 test.run 别名进入标准观察；扩展碰撞治理仍需补齐|
|成功测试后仍显示旧失败|逆向扫描遇成功 test.run 即停止，已修；验收失败反馈是独立新问题|
|验收完全信任 Agent 自报|已有冻结测试、候选副本、真实 diff 和独立执行；但语义验收不完备|
|完全缺乏 checkpoint/resume|已有保守恢复及 CLI resume；不支持不确定副作用自动恢复/HITL/版本迁移|

## 是否值得引入框架

仅维持短时单 Agent CLI，方案 A 足以修复上述大部分问题，没有必须引入框架的理由。如果路线图明确要求人工审批、长任务恢复和工作流扩展，F07–F09 形成部分迁移的充分理由。建议先完成接口、规则及测试基线治理，再以 LangGraph 做可撤销试点。框架收益应以“移除了多少自研编排与恢复胶水、保留了哪些安全不变量、故障恢复是否改善”衡量，而不是框架代码占比。
