# Runtime 优化实施记录

## 已执行

- D0：产物读取显式 UTF-8、pytest 真实模型 transport 拦截、确定性 smoke 契约。
- 修正后基线：502 passed、2 skipped、1 warning，470.42 秒。跳过项均是 Windows 符号链接能力不可用；警告是 Pydantic TestRun 非 pytest 测试类。
- UTF-8 定向复测：2 passed，13.95 秒；新增 smoke/离线保护：2 passed，29.25 秒。
- 已采集 20 次轻量 Fake 基线，见 performance-before.json；尚无优化后对比，不能据此宣称性能达标。
- D1：生产 verifier 必需；验收失败统一观察、修复来源区分、早期拒绝进入 implementing；新增验收覆盖报告与 CLI 覆盖数量。运行器/自修复/集成/验收定向测试 37 passed。
- D2：配置化上下文硬限额，包含模型 schema 预留与发送前校验；过大必要内容拒绝派发；显式工具别名及碰撞检测，运行路径归一；相关套件 64 passed。另补发送前 schema 与超长计划测试。

## 尚未完成

- D1 终态保存分支进一步收敛，以及提前验收失败时覆盖报告完整性检查。
- D2 完整产物引用策略和更多压缩优先级边界验证。
- D3 全部受管子进程统一、准备/评估预算的实际执行。已添加配置字段不代表这些限制已生效。
- D4 RunRequest/RunOutcome/RunSession、composition、公共测试服务、候选副本一致性与 EvalRunner 解耦。
- D5 ArtifactStore、诊断预留执行、checkpoint 版本升级及故障矩阵。
- D6 最终全套回归、八题 benchmark 正负例、20 次优化后性能对比、发布文档。

本记录不是完整交付声明；没有运行收费模型或修改 ShopFlow。

## 本地提交受阻

Git 索引写入被文件系统权限阻止。申请写入权限时，自动审批返回用量限制导致审核无法完成；不是安全拒绝。未绕过审核，也未创建提交。工作区改动保留，原有用户文档未修改。
