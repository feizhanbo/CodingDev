# P2：公共运行边界和 Session

涉及 `devpilot/devpilot/` 下：runtime/contracts.py、runtime/custom/session.py、application/runtime.py、evals/runner.py。

RuntimePort 仅包含 execute/resume；RunRequest 携带任务、用途、可信起点、冻结策略；RunOutcome 携带结果、路径、证据、统计、预算与状态。CustomRuntime 每次构建独立依赖；RunSession 保存本次可变状态和服务引用，客户端/锁/句柄不进入检查点。旧 Runner 门面拒绝同实例并发以防状态交叉。

验证：无 sandbox/verifier/metrics/deadline 内部属性的 MinimalRuntime 完成评估；两个运行的预算、缓存、验收证据隔离；旧版本检查点只读不恢复。

回退：按本单元职责撤回，保留已验证的权限修复；不删除运行目录或旧证据，不转换检查点版本。完整结果见 [交付记录](README.md)。

## 调用示例（仅 Fake smoke）

```python
from devpilot.application.runtime import CustomRuntime
from devpilot.domain.task import DevelopmentTask
from devpilot.runtime.base import FrozenPolicy, RunRequest, RuntimeConfig

policy = FrozenPolicy.from_config(RuntimeConfig())
runtime = CustomRuntime(config=policy.config(), fake=True)
outcome = await runtime.execute(RunRequest(
    task=DevelopmentTask(id="SMOKE", title="Repair addition", description="Fix addition",
                         acceptance_criteria=["Must add tests"]),
    purpose="ordinary",
    policy=policy,
))
print(outcome.result.status, outcome.evidence, outcome.budget)
```

评估器通过 `workspace_start` 传入起点，通过公开 `evidence/statistics/budget` 取回验证数据，不读取 Runner 内部属性。`resume` 使用构造 Runtime 时的相同配置/提供方；配置或源码身份不匹配时拒绝执行。`failure.json` 存在时，即使保留了早期 ready 检查点，也拒绝自动恢复。
