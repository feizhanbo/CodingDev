# P1-B：进程和全流程预算

涉及 `devpilot/devpilot/` 下：processes.py、execution.py、runtime/budget.py、runtime/custom/recovery.py、tools/code、tools/git、tools/test、verification。

统一 stdin、独立 stdout/stderr、有界输出和进程树清理。保留 Windows Job 启动握手和 POSIX 进程组。准备流程与同步写入使用可等待清理的工作线程，不取消等待后放任后台继续写。v2 检查点持久化全流程截止时间和已用验收预算。

验证：tests/test_processes.py、累计验收/准备超时/停机预算/不确定工具恢复契约。

回退：按本单元职责撤回，保留已验证的权限修复；不删除运行目录或旧证据，不转换检查点版本。完整结果见 [交付记录](README.md)。
