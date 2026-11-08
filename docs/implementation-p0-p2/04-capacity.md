# P1-C：容量和持久化

涉及 `devpilot/devpilot/` 下：storage.py、workspace/sandbox.py、tracing/writer.py、processes.py、Runner 产物路径。

物理文件计数、原子替换峰值、诊断保留额度和跨进程锁/预留记录统一准入。Git 捕获日志归属运行工作区/产物；工具执行同步核对工作区与产物容量。磁盘/配额失败不能产生截断但看似有效的检查点。

验证：tests/test_persistence.py、tests/runtime/test_recovery.py、替换峰值/异常退出锁回收/Trace 写盘失败边界测试。

回退：按本单元职责撤回，保留已验证的权限修复；不删除运行目录或旧证据，不转换检查点版本。完整结果见 [交付记录](README.md)。
