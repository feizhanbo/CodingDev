# LangGraph / LangChain 最终验收

2026-11-08。范围：P0–P5，默认编排切换为 LangGraph，模型适配切换为 LangChain，保留 custom/OpenAI 一个兼容发布周期。Langfuse 延后；用户明确要求跳过 Linux 验收，本轮仅验证 Windows。

| 要求 | 最终证据 |
| --- | --- |
| 基线与回退 | pre-langgraph-baseline 归档及 p5-baseline-integrity.json；旧环境恢复测试 p5-archived-recovery.txt；明确不支持任意 checkpoint 跨引擎转换 |
| 应用边界 | ApplicationRuntime / RuntimePort；CLI 与 Eval 通过应用层装配；CustomRuntime 兼容别名保留 |
| LangChain 适配 | 复用协议与解析器；最终全套包含适配器及 MockTransport 测试，覆盖取消、参数和记账；未进行付费模型能力验收 |
| LangGraph 编排 | 真实 StateGraph；最终全套包含拓扑、预算及 16 个复用业务契约用例 |
| 持久化恢复 | SQLite、回执、manifest 和预算对账；最终全套包含 7 个进程强杀边界、7 个图恢复用例、版本漂移及旧路由测试 |
| 默认切换与回退 | Settings 默认 langgraph/langchain；默认装配、显式 custom/OpenAI、Fake 优先级及历史路由检查通过；现有 run 依 manifest 恢复 |
| 全量回归 | runs/p5-default-full.txt/xml：634 passed、2 skipped，636 cases，零失败/错误；跳过项为 Windows 不支持的符号链接检查 |
| 静态检查 | runs/p5-default-lint.txt：All checks passed |
| ShopFlow | runs/p5-shopflow-final.txt/xml：67 passed |
| Benchmark | runs/p5-benchmark-final.txt：DEV-001 至 DEV-008 全部 PASS；这是确定性数据集验收，不是模型解题成功率 |
| 打包 | runs/p5-default-wheel-integrity.json：151 个包内 Python 文件与源码一致；runs/p5-default-source.json 保存 238 个文件哈希 |
| 安装及恢复 | runs/p5-default-install.txt：源码外安装、CLI、包资源、双运行时契约及图运行中断后新入口恢复全部通过 |
| 性能 | 十组交替配对业务结果一致；完整数据与取舍见 performance-decision.md；不以 Fake 样本推断真实模型延迟或并发容量 |
| 使用与兼容说明 | 根目录及 devpilot README、runtime-usage.md、.env.example 已同步新默认值，明确历史任务、回退、性能和平台限制 |

最终 wheel：`runs/p5-default-wheel/devpilot-0.1.0-py3-none-any.whl`。
SHA-256：`547d03286b1a72a2e84eaf7f1ac89355265cb4767f98eefc7b4fafa3e4348f94`。

显式回退新任务：`--runtime custom --llm-backend openai`。历史任务仍需原配置、版本、工作区和完整工件；不能通过改默认值将图 checkpoint 转为 custom checkpoint。旧归档恢复的证据仅覆盖保留的匹配环境。

本轮交付为本地代码与验证产物，未提交、推送或发布远端版本。Linux 未验证，Langfuse 未接入；这两项按用户范围安排不属于本轮未完成工作。
