# LangGraph / LangChain 迁移期间使用说明

当前默认是 `langgraph` 编排与 `langchain` 模型适配器，两者仍可以分别显式选择。
`custom` / `openai` 保留一个兼容发布周期；Langfuse 暂不接入。
默认切换后的最终验收已通过，证据见 final-acceptance.md。

## 安装与选择后端

在项目根目录使用锁定依赖安装：

```powershell
uv sync --project devpilot --frozen
```

运行现有 issue 文件时，显式选择两个后端：

```powershell
uv run --project devpilot devpilot run <issue.yaml> --runtime langgraph --llm-backend langchain
```

使用 `--fake` 可执行确定性的离线流程。Fake 模型优先于模型适配器设置，
因此 `--fake --llm-backend langchain` 不会验证真实 LangChain 模型传输。
模型传输的离线验证位于 `tests/llm/test_langchain_transport.py`，使用真实 SDK
和内存 HTTP 响应，不需要提供真实服务密钥。

环境配置对应 `DEVPILOT_RUNTIME`、`DEVPILOT_LLM_BACKEND`，模型连接仍使用
现有 `DEVPILOT_API_KEY`、`DEVPILOT_BASE_URL`、`DEVPILOT_MODEL`。保持原任务的
预算、测试解释器和工作目录配置，以便恢复时通过一致性校验。

## 查看与恢复

```powershell
uv run --project devpilot devpilot inspect <run_id>
uv run --project devpilot devpilot resume <run_id>
```

新运行的 `run-manifest.json` 记录编排后端、模型适配器和相关依赖版本。
恢复入口根据清单选择后端；运行锁内再次校验清单、代码/环境身份和文件摘要。
图运行通过 `graph.sqlite` 恢复状态，通过 `operations` 中的回执核对模型、工具和验证操作。
请保留完整运行目录、工作区及冻结验证证据，不能仅复制 SQLite 文件。

恢复保留原截止时间和已扣请求次数，不重置预算。模型请求的未知用量继续标记为未知。
已完成操作可复用；工具或验证操作结果不确定时会停止自动恢复，需要人工检查。
已发布终态结果、环境或证据不匹配、评估运行等情况不按普通中断运行恢复。

缺少清单的旧 custom 检查点通过格式和身份校验后，使用历史的 custom/OpenAI 后端。
缺少清单的图检查点会被拒绝，不能根据当前默认配置猜测其来源。
旧检查点不应直接交给修改后的代码，也不应手改身份、版本或预算字段绕过校验。
已保留旧源码与环境的恢复测试通过，但这不等于任意历史检查点可迁移到新引擎。

## 回退与验收范围

新任务可以显式使用 `--runtime custom --llm-backend openai`。这是后端选择，
不是将现有图检查点转换成 custom 检查点。历史任务应使用其匹配的保存环境。

当前已有 Windows 单元/集成回归、进程强制终止恢复、源码目录外 wheel 双引擎验证。
十组配对性能测量及默认切换后的回归、安装包验收均已通过。用户已要求本轮跳过
Linux 验收，因此本轮仅验证 Windows；Linux 尚未验证，不阻塞本轮交付。
具体证据和未完成项见 `implementation-status.md` 与 `remaining-gates.md`。
## 本地性能实测

十组交替执行的 Fake 模型 smoke 配对均得到一致的业务结果。Custom / LangGraph
执行中位数分别为 65.70 / 84.89 秒，配对相对耗时增幅中位数为 37.00%。图运行
每次产物约 1.46 MB，custom 约 80 KB；增量主要来自约 1.35 MB 的 SQLite 数据库。
耗时波动较大，这些数字不能预测真实模型延迟或长任务、并发任务的容量。
当前本地单任务用途的成本取舍见 [性能决策](performance-decision.md)。

