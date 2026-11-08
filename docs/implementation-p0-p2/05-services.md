# P2：应用层、公共 testing 和服务

涉及 `devpilot/devpilot/` 下：application/bootstrap.py、testing/junit.py、testing/suite.py、runtime/custom/services.py；现有 ContextBuilder、StateManager、LoopGuard。

从 CLI 移出任务加载和组件装配，保留兼容导出。公共 testing 不导入 evals；数据集 fixtures 由 evals 兼容包装器显式注入。决策、工具执行和独立验收服务由 Runner 顺序调用，原上下文、状态与守卫服务继续复用。

验证：CLI、任务加载、工具和验收回归；公共 testing 依赖检查与框架独立性测试。

回退：按本单元职责撤回，保留已验证的权限修复；不删除运行目录或旧证据，不转换检查点版本。完整结果见 [交付记录](README.md)。
