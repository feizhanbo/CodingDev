# DevPilot 架构审计与框架重构方案

日期：2026-10-24。基线：`41b027b4860354f69205ed7895de044b7f2bd39e`。**本轮仅分析、验证和设计，到方案评审为止；没有实施重构。**

推荐：先修复缓存鉴权、通用进程/预算执行和模块边界，再以 **LangGraph 局部接管编排**。保留现有 LLMClient、工具执行、工作区、确定性测试、冻结验收和 Benchmark。若试点收益不足，继续优化后的 custom Runtime，不强制整体替换。

## 阅读顺序

1. [当前项目真实架构与运行机制](G:/program/CodingDev/docs/architecture-review-2026-10-24/01-current-architecture.md)：证据索引、当前架构、调用链、状态与实际完成度。
2. [问题与重构必要性](G:/program/CodingDev/docs/architecture-review-2026-10-24/02-problems-and-necessity.md)：历史结论重新核对、12 项问题的根因/影响/责任归属。
3. [框架选型对比](G:/program/CodingDev/docs/architecture-review-2026-10-24/03-framework-selection.md)：LangGraph、PydanticAI、AutoGen、CrewAI，补充 Microsoft Agent Framework；三条路线与推荐依据。
4. [目标架构设计](G:/program/CodingDev/docs/architecture-review-2026-10-24/04-target-architecture.md)：当前/目标图、执行流程、模块映射、接口/状态、checkpoint 与副作用对账。
5. [分阶段迁移计划](G:/program/CodingDev/docs/architecture-review-2026-10-24/05-migration-plan.md)：P0–P5 的路径、任务、依赖、工作量、测试、切换门槛和回滚。
6. [本次验证记录](G:/program/CodingDev/docs/architecture-review-2026-10-24/06-validation.md)：命令、版本、测试数据、专项探针和未验证项。

## 关键结论

- 当前不是原型空壳：请求预算、别名治理、冻结原测试独立验收、普通任务保守恢复已有实现与离线覆盖；不能继续沿用“完全缺失”的旧审计结论。
- 首要缺陷有具体证据：read_file 缓存先读取后鉴权；五个资源配置没有执行端消费；Git/rg 生命周期未统一治理；多数自然语言验收条件仍未覆盖。
- 框架最适合改善集中编排、显式分支与持久人工中断；安全隔离、业务验收与预算规则仍由 DevPilot 负责。
- 采用“公共服务 + 两种薄 Runner”的短期并行方式，避免维护两套工具和验收。旧检查点须由原发行环境恢复，不自动转换为新图。
- ShopFlow 业务与评估资源保持；仅将硬编码项目规则从通用 Prompt 中分离为后续独立改进。

## 本次验证结果

| 验证 | 结果 |
|---|---|
| DevPilot pytest | **511 passed / 2 skipped / 1 warning**；两项 skip 均因本环境无法创建符号链接 |
| 八任务 Benchmark 自检 | **8/8 通过**；缺陷负例、参考修复隐藏测试与可见测试；非模型能力成功率 |
| Ruff | **14 项现存问题**，未改代码修复 |
| 专项探针 | 确认缓存越界预读、直接 code→test 后 phase 滞后 |
| 真实模型/新框架性能 | 本轮未调用、未验证，不声称收益 |

## 评审决策建议

先确认 P0/P1：冻结基线与修复独立工程问题；P2 收紧服务/评估契约后，再决定进入 LangGraph 试点。全路线估算 **24–38 人日**，不含 OS 隔离、新审批产品 UI、收费模型评测和发布排期。可在 P2 停留方案 A；不预先承诺大范围重写。

