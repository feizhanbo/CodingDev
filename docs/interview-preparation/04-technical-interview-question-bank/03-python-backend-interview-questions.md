# Python 后端专项

## B01｜P0·中级｜用本项目解释 coroutine、Task、Future 和 await。

**考察**：异步执行模型。**简答**：async 函数调用产生协程；Task 调度协程，Future 表示待完成结果；await 等待可等待对象，允许事件循环继续处理其他可运行任务，不保证每次都切换。

**展开**：run_cancellable 把 to_thread 协程包装为 Task 并保留引用，等待同步 worker 的结果；同步阻塞工作不应直接占住事件循环。当前图仍串行，异步主要帮助 I/O 等待及取消协调，不表示节点并行或 Python CPU 计算提速。

**原理/追问**：典型带 GIL 的 CPython 下线程不能自动加速纯 Python CPU 密集循环；to_thread 主要用于这里的阻塞操作，进程可独立执行 CPU 工作。追问取消这个 Task 能否杀线程？B02。

**证据**：P，原理参考 README 官方资料。**评价**：合格区分协程和 Task；深入能指认真实 worker；“await 开新线程”错误。

## B02｜P0·高级｜wait_for 超时为何还要 shield 和 Event？

**考察**：取消与资源所有权。**简答**：取消等待者不能强杀线程。项目保护 worker，通知 Event，再等它停止进程树与清理资源，最后重新传播取消。

**展开**：run_cancellable 捕获 CancelledError 后 cancel.set，循环 shield 等待并处理重复取消；worker 异常被取回，但原取消保持权威。run_process 监视取消并关闭 Windows Job 或 Unix 进程组。实际返回可能晚于 timeout；不检查 Event 的阻塞函数仍可能拖住清理。

**原理/追问**：wait_for 请求取消而非瞬间终止；为什么不直接吞掉取消返回失败 ToolResult？会破坏上层生命周期语义。继续 T4。

**证据**：P、B，test_cancellation_waits_for_owned_process_cleanup。**评价**：深入能区分协程/线程/进程三个层次；“超时自动杀全部子进程”错误。

## B03｜P1·中级｜上下文管理器、异常和装饰器如何出现在项目中？

**考察**：资源与作用域。**简答**：RunBudget.evaluation 用 contextmanager 在进入时设有效 deadline，finally 累加耗时；RunLock 用进入/退出控制锁。异常退出也要完成资源清理。

**展开**：with 不天然吞异常，取决于退出处理；普通 Exception 不包含 CancelledError。Registry 有些异常转结果，但 ArtifactQuotaExceeded 重抛。OrderService 的 staticmethod 不接收实例 self，依赖通过 Session 参数传入，不意味着数据库操作没有状态。

**原理/追问**：finally 能否应对 kill -9/进程强杀？不能保证；需要 OS 所有权与恢复证据。继续 S01。

**证据**：B、F、D。**评价**：合格知道 finally；深入说明异常类型与强杀边界；宣称 finally 永远执行错误。

## B04｜P0·中级｜Session、flush、commit、rollback 如何保证下单原子性？

**考察**：事务范围。**简答**：get_db 每请求提供 Session 并 finally close；Repository flush 执行未提交 SQL，Service 把库存、订单、明细统一 commit，失败则 rollback。

**展开**：flush 可获得订单 ID，但不是小提交。若 Repository 提前 commit，后面失败无法撤销前面成功。ACID 在这里对应整体提交、业务约束维护、数据库并发隔离和提交持久性；业务一致性仍需要条件 SQL 和验证，不是数据库替你理解订单规则。

**原理/追问**：已 commit 后 refresh 失败呢？rollback 不撤销已提交事务，S06。Session 也维护对象状态，不应跨并发任务任意共享。

**证据**：D，test_failure_rolls_back_everything。**评价**：合格说出事务边界；深入区分提交前后；“close 自动成功提交”错误。

## B05｜P0·中级｜库存条件 UPDATE 比先查库存再写好在哪里？

**考察**：原子条件与并发。**简答**：`WHERE id=? AND stock+delta>=0 SET stock=stock+delta` 将判断和扣减放进一条 SQL，并检查 rowcount，不依赖应用旧读值写回。

**展开**：创建前先按商品聚合数量；扣减和订单仍在一个事务。SQLite 写者竞争可能锁失败，条件更新不承诺请求都成功。它防这个更新路径扣成负数，不保证其他任意 SQL 路径也遵守约束。

**原理/追问**：CAS 与版本锁区别？这里以业务状态/数量作条件，未使用 version_id 版本列。为什么不用 Redis？D04。

**证据**：D，test_concurrent_orders_do_not_oversell。**评价**：深入会提 rowcount 和 rollback；“解决所有并发问题”错误。

## B06｜P0·中级｜重复支付、重复取消与请求幂等有什么不同？

**考察**：幂等语义。**简答**：支付只允许 pending→paid，重复支付拒绝；取消成功迁移才回补，已取消再次返回状态、不重复加库存。下单没有请求幂等键。

**展开**：幂等副作用指重复请求不产生额外业务效果，不必每次同一 HTTP 响应。状态 CAS 不能识别两个不同请求是否表达同一业务意图；提交成功响应丢失后重试 create 仍可能创建新订单。

**原理/追问**：退款 API 怎么办？扩展需远端幂等键和对账，不放进本地数据库事务就宣称原子。继续 T6。

**证据**：D，test_cancellation_restores_stock_once。**评价**：深入区分效果、响应与请求身份；把重复支付返回冲突说成完整幂等设计不准确。

## B07｜P1·高级｜SQLite 锁、事务隔离和 MVCC，哪些是项目实际用到的？

**考察**：数据库知识边界。**简答**：项目依赖 SQLite 事务及条件更新，不配置生产级隔离方案；SQLite 同一时刻单写者，API 对部分 locked/busy 错误返回503。

**展开**：MVCC 是多版本可见性机制，不代表写入无需锁；不能拿 PostgreSQL 行版本机制解释本项目所有 SQLite 行为。当前未显式开启 WAL，不把 WAL 的读写并发特点当成果。索引、事务长度与忙等待仍影响性能。

**原理/追问**：迁移 PostgreSQL 时要重新测试隔离级别、锁等待、死锁/序列化失败重试、连接池和 SQL 类型；Read Committed 下并发 UPDATE 对最新可更新行重新判断条件，不等于多语句业务自动串行化。

**证据**：D；[SQLite](https://www.sqlite.org/isolation.html)、[PostgreSQL 事务隔离](https://www.postgresql.org/docs/current/transaction-iso.html)。**评价**：明确扩展与当前；“MVCC 不加锁”是盲区。

## B08｜P1·高级｜gather、TaskGroup、Semaphore 会怎样用于扩展任务并发？

**考察**：结构化并发；这是扩展设计，当前图不靠这些实现并行节点。

**简答**：需先隔离每 run 工作区和依赖，再限制准入。若子任务命运相连，TaskGroup 更便于失败时取消并等待同组任务；gather 默认首个异常传播时不自动取消其余任务。

**展开**：Semaphore 只限制当前进程并发名额，不是集群配额；TaskGroup 的异常会聚合，但仍需底层进程清理协议。不能把共享 runner/session 放进 gather 就认为并发安全。

**原理/追问**：部分任务应继续、部分应一起失败如何处理？先定义任务独立性，再选收集错误或组取消，不盲目套 API。

**证据**：R/P 是当前隔离与清理依据；[Python 3.12 官方语义](https://docs.python.org/3.12/library/asyncio-task.html)。**评价**：深入能说出异常后兄弟任务行为和进程边界；声称已实现集群 Semaphore 不实。

## B09｜P1·中级｜接口抽象和依赖注入怎样降低框架耦合？

**考察**：后端结构设计。**简答**：RuntimePort 定义 execute/resume 契约，ApplicationRuntime 每次构建依赖，CLI/Eval 只消费 RunOutcome，而不读取具体 runner 内部字段。

**展开**：Protocol 是结构化类型接口，不自动创建对象；bootstrap 是显式装配点。frozen dataclass 限制属性赋值，不保证内部 dict 深度不可变。将依赖方向指向领域契约、把具体引擎导入留在装配边界，可以减少循环依赖，但不宣称全仓库完全无耦合。

**原理/追问**：为何共享代码还要契约测试？编排顺序与错误路径仍可能不同，见 D01。

**证据**：R，test_application_entrypoints。**评价**：深入解释对象寿命与状态隔离；只背 SOLID 名称不够。
