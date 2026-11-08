# DevPilot 架构问题与重构必要性

基线与 E01–E15 证据编号见 [当前架构报告](G:/program/CodingDev/docs/architecture-review-2026-10-24/01-current-architecture.md)。严重性定义：P1 为当前可靠性或权限边界优先修复项；P2 为维护、可扩展性和解释一致性问题；P3 为清理项。此分级基于可信本机使用范围；若要执行不可信仓库，OS 隔离是发布前置条件。

## 1. 历史结论重新核对

| 历史问题 | 本次核对 | 剩余问题 |
|---|---|---|
| 模型重试绕过预算 | 已修：SDK max_retries=0；每次请求前递增；恢复保留尝试数；有 request_budget/recovery 测试 | 未实现全局 Token/费用预算，准备阶段计时不完整 |
| 敏感文件搜索 | 已修：search_code 在 rg 与 fallback 前统一过滤 | read_file 缓存先读后鉴权；Git/子进程策略仍需统一 |
| 工具别名绕过守卫 | 已修：注册冲突检查；决策进入业务处理前 canonical_name | Context 中仍有冗余旧别名兼容，可在兼容期后清理 |
| 上下文丢失验收失败状态 | 已修：repair_sources 和 verification_report 独立持久；开发测试通过不清除验收失败 | 阶段推断仍不准确；Prompt 与截断策略存在冲突 |
| 原测试可被模型修改以蒙混验收 | 已大幅补强：冻结基线、写保护、重新物化、外部测试 harness | 同用户恶意代码不受 OS 隔离；需求覆盖不完整 |
| 完全没有断点恢复 | 已不成立：checkpoint + resume 已接入 CLI 和测试 | 执行中工具/验收拒绝恢复；无人工审批状态、无副作用对账 |
| 评估直接 import CustomAgentRunner | 已修直接导入：协议 + 注入工厂 | 仍通过对象属性读写内部实现，边界只完成一半 |

## 2. 问题清单：表现 → 根因 → 影响 → 处理

### P01 / P1：缓存读取绕过前置路径授权

- **实际表现**：`runner.py:512–523` 在 Registry/ReadFile 校验前调用 ReadFileCache.get；[file_cache.py:27](G:/program/CodingDev/devpilot/devpilot/tools/repo/file_cache.py:27) 使用未经校验的路径 `read_bytes()`。临时目录合成探针请求 `../audit-sentinel.txt`，观察到越界文件被读取一次，随后工具拒绝；没有内容返回。见 [探针输出](G:/program/CodingDev/docs/architecture-review-2026-10-24/audit-probes.txt)。
- **根因**：Runner 为性能优化承担了原本属于受控工具的 I/O，信任校验发生在后面。
- **影响**：越界/敏感文件可发生非授权本地读取和内存消耗；不能据此夸大为已证明向模型泄露内容。特殊文件、超大文件可能引入额外可用性风险，未对真实敏感资源做探测。
- **框架必要性**：无。换框架若原样搬缓存，会保留缺陷。
- **推荐**：缓存移到 ReadFile 内部，在 PathGuard 校验后的规范路径上工作；设置文件读取字节上限；取消 Runner 的缓存旁路。回归测试断言“拒绝时零文件读取”，不能只检查 ToolResult.error。

### P02 / P1：资源配置有字段但没有执行语义

- **实际表现**：E02 的五个字段只见声明和校验。Runner 对普通工具使用全运行 `_remaining()` 而非 tool_timeout_seconds；准备阶段先执行同步 copy/hash/git，之后才建立运行 deadline；隐藏验收使用 test_timeout_seconds 与剩余运行时间，而不是 evaluation_timeout_seconds。
- **根因**：预算配置扩展没有沿服务边界完整传递；“逻辑 timeout”与进程取消、I/O 限制未统一。
- **影响**：用户设置更小的通用工具/准备/评估限额不会得到相应限制；准备过程可超出 max_run_seconds 所暗示的总时长。`max_context_chars` 仅限制模型输入，无法限制先加载进内存的工具数据。
- **框架必要性**：框架节点 timeout 可辅助，但不解决阻塞 I/O/进程生命周期。先修业务预算服务。
- **推荐**：建立 BudgetLedger/ExecutionPolicy，明确 preparation、active、evaluation 三段 deadline 和 overall deadline；每次操作使用阶段和全局最小剩余值；不生效的字段应实现或显式拒绝，而非静默接受。

### P03 / P1：测试进程治理与 Git/搜索进程治理不一致

- **实际表现**：E10 有完整 run_process/run_cancellable；E08 搜索及 E09 补丁、[git/diff.py:59](G:/program/CodingDev/devpilot/devpilot/tools/git/diff.py:59)、status、create_file 的 git add 使用 `create_subprocess_exec(...).communicate()`，没有相同输出限额或取消后 kill/wait。准备阶段 `_git`、`materialize_candidate` 还有无 timeout 的同步 subprocess.run。
- **根因**：各工具自行启动进程，没有统一受控 ProcessExecutor。
- **影响**：取消 await 不等于停止子进程；补丁回滚与尚未结束的 Git 写可能竞争。搜索逐文件启动 rg，且先完整缓存单文件输出再截断 matches；长行/大文件可使输出限制失效。这里是源码确认的未受控路径，不声称已复现失控写盘。
- **框架必要性**：无，框架取消节点不能替代 kill/wait。
- **推荐**：让所有进程经统一执行器，支持 stdin、分离 stdout/stderr、输出上限、deadline、环境过滤和进程树清理；取消后先确认进程退出，再回滚文件。保留现有 Windows Job 与测试执行经验。

### P04 / P1（不可信输入部署条件）：可信本机不等于安全沙箱

- **实际表现**：候选 Python/pytest 以宿主权限运行，网络未被强制阻断。trusted/hidden 测试在工具可见路径外，但同一用户代码可直接访问文件系统。E08/E10/E12 注释和 AgentRunResult 已如实声明。
- **根因**：当前边界是受控工具与独立目录，不是独立用户、容器/虚拟机或内核策略。
- **影响**：不应把现有模式扩展到任意互联网仓库或多租户。冻结测试防普通改测行为，不防恶意同用户代码。
- **框架必要性**：无。任何候选框架都不能自动修复。
- **推荐**：现有可信本机模式继续明确呈现能力；若产品需要不可信执行，独立立项 ProcessExecutor backend：只读 trusted 挂载、临时候选卷、网络策略、资源额度、凭据隔离。该项与 Agent 编排迁移独立验收。

### P05 / P1：通过测试与满足任务要求之间仍有缺口

- **实际表现**：E12 `coverage_for:296` 对一般条件标记 uncovered，`verify:201–204` 成功由 checks 决定，未要求所有条件已覆盖；“新增测试”只检查存在新增测试且相关 suite 通过，不证明测试对应特定业务需求。
- **根因**：DevelopmentTask.acceptance_criteria 是字符串列表，缺少可信 criterion→deterministic check 的绑定。
- **影响**：completed 的含义应限定为“当前已配置验收通过”。普通任务没有隐藏测试兜底；框架 output validator 只验证数据形状。
- **框架必要性**：无。需要验收领域设计和任务数据。
- **推荐**：引入 AcceptanceSpec(check_id、criterion_id、required、evidence_ref)；默认兼容现有未覆盖展示，strict 模式要求每个必选条件有证据，否则 needs_review/失败。新增代码不能靠一个 LLM judge 推翻冻结测试失败。行为变化与 Runtime 替换分阶段，防止混淆成功率。

### P06 / P2：编排与可变运行状态集中于 Runner

- **实际表现**：E03 同时承担准备、模型重试、工具缓存、预算、阶段推断、测试修复、验收、恢复、追踪和文件持久化；构造器需要大量协作者，运行时又修改 self.request_count/deadline/metrics/loop_guard/verifier 等。
- **根因**：按功能增量扩展 `_run`，缺少每次运行独立 Session 与稳定服务接口。
- **影响**：新增人工暂停/多流程需在多个嵌套分支同步改动；同一 runner 实例并发 run 会共享/重置内部状态，RunLock 只按 run_id 锁，不能防该问题。现有 run_all 顺序执行，所以不是已验证的生产并发事故。
- **框架必要性**：显式图对分支/生命周期有帮助；服务抽取本身不依赖框架。
- **推荐**：先拆 RunSession、DecisionService、ToolExecutor、VerificationService、RunRepository，再令两种 Runner 使用相同服务；框架只处理节点路由和图状态。

### P07 / P2：phase 不是可信执行状态，计数语义混杂

- **实际表现**：E03 `_maybe_advance_phase:768` 根据工具前缀/步数推断；直接 code→test 仍可处于 understanding（探针确认）。E11 验收失败直接赋值 implementing；规划允许跳过；观察反馈增加 total_steps；测试失败和验收拒绝共用 retry_count。
- **根因**：显示阶段、控制节点、业务证据与预算共用字段；计划状态又由模型自报。
- **影响**：Prompt 可能要求探索但实际已修改；图迁移若把每个节点计为旧 max_steps，会悄然缩减任务预算。
- **框架必要性**：适合用显式条件边解决调度；业务字段与计数定义仍由 DevPilot 决定。
- **推荐**：区分 lifecycle/status、next_node、display_phase、domain_steps、request_attempts、test_failures、verification_failures；兼容模式保留旧计数，版本化引入更准确新计数。计划只是意图，不作为已完成证据。

### P08 / P2：已有恢复过于保守且成本随运行增长

- **实际表现**：E14 ready/llm_inflight 可恢复；tool/verifier inflight 拒绝；runtime_identity 对包内源码整体哈希；每次 checkpoint 对工作区（含 Git、生成文件）及 trusted 全量读文件哈希并保存完整 state/metrics/guard。
- **根因**：为避免未知副作用重放，采用粗粒度一致性校验，缺少操作日志、内容寻址产物和稳定的执行 schema。
- **影响**：正确地拒绝不安全恢复，但 benign 源码变更也拒绝；大仓库多轮哈希和重复 JSON 写放大成本；没有人工暂停的生命周期语义。
- **框架必要性**：checkpoint/interrupt 调度值得交给框架；文件修改的幂等/对账不可交给图保存器自动推断。
- **推荐**：LangGraph 提供图进度；DevPilot 继续持有 operation journal、文件前后指纹、身份/版本校验和 run 锁。未知副作用仍 fail closed，不承诺 exactly-once。设计见目标文档。

### P09 / P2：评估替换缝隙存在，契约仍泄漏内部状态

- **实际表现**：E13 通过 runner_factory 注入，却修改 sandbox/purpose，读取 verifier.last_results、metrics、deadline；E02 AgentRunner 用 Any，未声明实际消费的所有成员。E12 与 RunTests 反向依赖 `evals.benchmark` 的执行器/JUnit 解析。
- **根因**：复用以对象内部属性和包内工具函数实现，没有独立运行产物与测试基础设施边界。
- **影响**：新 Runtime 即便实现 `run(task)` 仍不能无缝评估；纯导入独立性测试无法发现该问题。
- **框架必要性**：无；引入任何框架前应先修。
- **推荐**：RunOutcome 中显式返回结果、证据引用、metrics 和预算快照；工作区通过 RunRequest 注入；公用 suite/JUnit 移到 testing，Benchmark 仅持数据集逻辑。评估只读 outcome/产物，不读取图状态或 Runner 私有对象。

### P10 / P2：上下文与提示策略限制通用性

- **实际表现**：E05 有 ShopFlow 专用规则；读文件结果只呈现 2000 字符且要求只读一次；模型 Prompt 限制重复两次，实际 Guard 为连续六次。修改后缓存会失效，但 Prompt 仍阻止合理重读。`_parse_decision` 的 JSON 包围提取逐字符数花括号，没有字符串转义状态。
- **根因**：演示任务经验固化在通用层；上下文预算、有效证据与模型协议混杂。
- **影响**：换仓库可能收到错误约束；长文件精确修改困难；宽容解析存在边界。未以真实模型衡量对成功率的影响，不能量化收益。
- **框架必要性**：PydanticAI 可减少结构化输出/provider 胶水，不能自动修复项目 Prompt。
- **推荐**：RepositoryProfile 注入规则；按版本+行区间记录证据，允许必要重读；结构化解析失败返回明确反馈并计预算；协议改造作为独立实验，不和编排改造同时进行。

### P11 / P2：配额、持久化、统计仍存在非原子边界

- **实际表现**：E09 diagnostics 文件跳过普通配额，diagnostic_reserve_bytes 未使用；TraceWriter 直接 append；单文件 atomic_write 不是跨文件事务。工作区总量用 permitted_files，过滤掉 Git 等，运行内增长只检查单 workspace 的允许文件。检查与并发写之间也无全局预留锁。
- **根因**：容量采用事前/事后估算，缺少统一磁盘记账与提交序号。
- **影响**：多个运行或大 diagnostics 可能超预期占用；Trace/State/Result 可能不在同一提交点。修复需要保留诊断可写性，而非简单禁止所有终态写入。
- **框架必要性**：数据库事务可帮助 checkpoint；总文件配额、日志上限和产物协议仍归宿主。
- **推荐**：有界诊断保留区、物理字节计数、受锁配额预留、幂等终态提交和报告投影；metrics 用显式定义而非从不同状态推断。修复请求失败计数/Token 未知语义时保留原始记录。

### P12 / P3：遗留分支与质量基线需要清理

- **实际表现**：TaskVerifier 的 `_check_visible_tests`/`_check_diff_non_empty` 与 EvalRunner 的 `_check_visible_tests` 不在当前主链路；部分常量/注释仍描述旧行为（例如 GitDiff 实际 diff HEAD）；本次 Ruff 发现 14 个现有问题。
- **根因**：安全加固替换执行路径后旧辅助逻辑未归并。
- **影响**：维护者易修错路径；当前 lint 基线不能声称全绿。
- **框架必要性**：无。
- **推荐**：按调用者及测试依赖逐项去除/迁移，先记录再建立无新增问题门槛；不要在本轮文档任务中顺手修代码。

## 3. 哪些能力适合交给框架

| 责任 | 推荐归属 | 理由 |
|---|---|---|
| 节点调度、条件边、分支汇合、图检查点、持久 interrupt | 编排框架 | 避免在大型 while 中持续叠加相同通用机制 |
| 请求/Token/时间预算规则、决定是否重试、阶段语义 | DevPilot 服务；框架执行调度 | 计费和业务语义不能被框架默认行为隐式改变 |
| 补丁、权限、路径、冻结测试、可信证据、验收标准 | DevPilot 确定性领域能力 | 是产品差异与安全边界，不是框架附属工具 |
| 子进程取消、OS/网络隔离、资源配额 | 执行基础设施 | 与 Agent 框架无关 |
| Benchmark、隐藏测试、成功率和回归计算 | 框架外评估层 | 必须能公平比较 custom 与新 Runtime |
| 模型输出解析、供应商接入 | 先保留；日后单独评估 PydanticAI | 现有接口可复用，同时迁移两层会扩大行为差异 |

## 4. 引入框架是否有充分理由

**足以支持低风险编排试点，不足以支持立即整体重写。** 已有可靠闭环和恢复能力，因此“从零获得 checkpoint”不是成立理由。价值来自持续增加的分支、恢复/人工介入和状态可解释性；若近期仍只做短任务单 Agent，先实施方案 A 的边界与工程改进即可。

推荐评审通过后先实施框架无关的 P0/P1 阶段，随后以 LangGraph 做方案 B 的并行可替换编排。若试点未降低新增工作流成本、恢复/调试收益不足或运行开销超门槛，停在优化后的自定义 Runtime 是有效结果。无需为了使用框架迁移已成熟的工具与验收。

