# DevPilot P0–P2 实施交付

本轮保留 custom Runtime、既有八个工具协议、CLI/YAML 与 `run(task)` 门面。未引入 LangGraph，未修改 ShopFlow 业务，未修改模型协议和 Prompt，未调用收费模型。Fake/Benchmark 自检不代表真实模型能力成功率。

## 六个审查单元

| 顺序 | 变更 | 审查说明 |
|---|---|---|
| 1 | P0 契约与质量基线 | [01-p0.md](01-p0.md) |
| 2 | P1-A 授权、缓存、有界读取 | [02-read-security.md](02-read-security.md) |
| 3 | P1-B 进程生命周期、全流程预算 | [03-process-budget.md](03-process-budget.md) |
| 4 | P1-C 物理容量、持久化与预留 | [04-capacity.md](04-capacity.md) |
| 5 | P2 应用装配、公共 testing 与服务 | [05-services.md](05-services.md) |
| 6 | P2 RuntimePort、RunSession 与评估解耦 | [06-runtime-port.md](06-runtime-port.md) |

这是工作区内的六个审查单元，未自动创建 Git 提交或发布远程变更。多个单元共同修改 Runner，回退须按对应职责撤回，不能直接用旧 Runner 覆盖权限修复。

## 运行契约

- 全流程 deadline 在准备开始前建立，涵盖准备、模型、工具、独立验收、隐藏测试和恢复停机时间。
- 准备使用全局/准备阶段剩余时间的最小值；工具使用全局/工具限制的最小值，pytest 额外受测试超时限制。
- 独立验收按实际耗时累计扣除 evaluation 额度，重试不重置；隐藏评估消费公开预算快照中的剩余额度。
- 读取每次先校验路径/敏感文件/链接，缓存按规范路径、范围、内容摘要及输出额度索引。文件修改即使保留大小和 mtime，也不会返回旧内容。
- 新检查点版本为 2，标记 `whole_task_v2`。版本 1 仍可解析/查看，但拒绝恢复。工具/验收处于执行中的检查点继续拒绝自动恢复。
- `uncovered` 判定保持原样，未增加严格验收模式；步数、修复计数与阶段规则保持原契约。

## 容量与取消边界

工作区/产物统计覆盖 Git、日志、数据库和生成文件。共享根目录使用 OS 锁进行串行准入，容量争用返回明确的 `shared_capacity_busy`，不会静默超售。预留记录只在持锁核对物理文件后回收，运行证据不被自动删除。

普通产物不能使用 `diagnostic_reserve_bytes`；替换文件需要同时容纳原文件及原子写入临时文件。配额失败不向临时目录导出完整状态/检查点；能容纳时只保存有界 `failure.json`，明确不可恢复。普通磁盘故障保留小型紧急诊断，返回持久化错误，不宣称成功。

取消会等待自己启动的进程树和 I/O 工作线程退出。补丁在进程清理后回滚；无法确认创建操作结果时返回 `manual_recovery_required`。这些是 trusted-local 下的协作式治理，不是对任意候选程序宿主写入的硬磁盘或 OS 隔离。

## 验证证据

- [基线版本与依赖](baseline.json)；[最终源码与 wheel 指纹](delivery-manifest.json)。
- [最终 Ruff](final-ruff.txt)：无问题。
- [完整 DevPilot 回归](pytest-validation.txt)：527 通过、2 跳过；此记录对应收尾容量修改前的完整通过基线。
- [最终收尾定向回归](final-focused.txt)：44 通过；[恢复标记回归](final-recovery-markers.txt)：3 通过。
- [最新完整回归记录](final-tests.txt)：528 通过、2 跳过、1 项旧测试外层 5 秒等待超时（发生在准备阶段）。该测试保持模型 10 毫秒/三次请求断言，将外层等待改为 30 秒后，[44 项定向回归](final-focused.txt)以及[单独复测](final-timeout-recheck.txt)均通过。没有尚未解决的已知测试失败；未再重复整套长耗时测试。
- [最终路径权限回归](final-path-security.txt)：17 通过、2 项链接测试因本机权限跳过，覆盖工作区根目录链接在内容读取前拒绝。
- [ShopFlow 回归](shopflow-tests.txt)：67 通过。
- [八任务 Benchmark](final-benchmark.txt)：8/8 自检通过。
- [源码目录外安装](final-wheel-install.txt)：wheel 安装、CLI、数据集及进程执行验证通过。

本机为 Windows。两个链接测试因创建链接权限不足跳过，须由 Linux CI 补齐。现有 `.github/workflows/ci.yml` 已配置 Windows/Linux 矩阵；本轮未向远程推送，也未声称 Linux CI 已执行。本机 WSL 未提供可用 Linux 发行版。

## 回退和下一阶段

保留用户工作区、历史报告和检查点。按六个单元反向撤回未经验证的改造；已经验证的授权修复独立保留。恢复功能不得用旧运行器强行载入 v2 检查点。LangGraph 试点评审属于后续 P3，本轮不自动启动。
