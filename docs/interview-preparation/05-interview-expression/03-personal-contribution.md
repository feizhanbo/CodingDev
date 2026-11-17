# 个人贡献与证据梳理

## 当前可确认的范围

仓库能确认实现与演进存在，但当前对话尚未确认用户身份与提交作者映射、参与程度或独立设计责任。因此下面是**可核实的贡献候选清单**，不是已确认个人履历。暂时没有条目可直接归为“已确认本人参与实现”。

| 贡献事项 | 项目模块 | 实际证据 | 可体现能力 | 个人参与程度 | 待确认信息 |
| --- | --- | --- | --- | --- | --- |
| 应用边界与图迁移 | DevPilot application/runtime、shared、langgraph | 41c4ea5；test_graph_business_contracts | 分层、渐进迁移、契约验证 | 待确认 | 提出方案/编码/评审分别由谁完成 |
| 独立验收 | DevPilot verification、testing、evals | 4a8a778；test_evidence、test_eval_truthfulness | 可信证据、指标设计 | 待确认 | 是否亲自设计保护规则或写回归测试 |
| 回执与恢复 | DevPilot operations、runner | OperationJournal；test_graph_resume | 故障建模与一致性 | 待确认 | 哪个崩溃窗口亲自复现，负责哪些路径 |
| 生命周期治理 | DevPilot budget、processes | f7ba445相关变更；当前run_cancellable；test_processes | 异步取消、资源所有权 | 待确认 | 是否实现Windows Job或只使用/验证 |
| 文件操作边界 | DevPilot PathGuard、ApplyPatch、Sandbox | dccd2ba；test_destroy_rejects_resolved_targets_outside_workspace | 文件系统与防御性校验 | 待确认 | 发现过程、修改和测试责任 |
| 上下文与修复反馈 | DevPilot ContextBuilder、StateManager | 41b027b；test_context_feedback | 数据反馈与有限预算 | 待确认 | 反馈缺失如何发现，是否亲自改字段契约 |
| 订单事务与状态 | ShopFlow OrderService、Repository | 34e6e7e；test_order_integrity | 事务、并发、故障注入 | 待确认 | 是否参与实现、测试或后续学习 |
| 中文恢复与产物保护 | DevPilot lifecycle | 05d26dc；中文恢复及ID冲突测试 | 跨环境排查、持久化协议 | 待确认 | 是否亲自遇到locale/碰撞问题 |
| 配置、打包与CI | DevPilot Settings、scripts、workflow | check_wheel.py、ci.yml、历史验收记录 | 工程化、发行验证 | 待确认 | 本人执行过哪些检查；未确认生产部署 |
| 框架与成本研究 | 架构选型、performance-decision.md | 文档明确候选选型未做PoC；后续本地配对测量记录 | 约束分析与测量判断 | 待确认，仅文档事实 | 谁做研究/测量，原始结果是否本人核对 |

具体文件与函数链接见[第二阶段源码索引](../02-core-technical-deep-dive/source-index.md)，历史前后差异见[第三阶段复盘](../03-engineering-practice-review/02-engineering-problem-retrospective.md)。

## 四种证据状态与可用主语

1. **代码/提交已确认**：可以说“项目实现了……”“该提交将……改为……”。
2. **本人确认参与、独立责任未确认**：确认后可说“我参与了……，具体承担……，整体方案由……共同确定”。目前尚无此类确认。
3. **只见设计文档或事后推导**：说“文档记录的考虑是……”或“从当前约束分析……”，不说“我当时比较后决定”。
4. **个人经历未确认**：保持【待确认】，不得自动使用“我主导”“我独立设计”“我排查线上事故”。

## 三种诚实表达模板

**确实实现过时**：“我主要负责【模块】中的【边界明确的功能】。我改了【代码点】，补了【测试】，用【断言】验证；【其他部分】由协作方完成。”

**只参与部分工作时**：“整体架构已有，我主要参与【适配/测试/修复】。我负责确认【具体契约】，没有主导完整选型。”

**属于复现学习时**：“这部分实现不是我独立设计的。我做了源码分析和【实际完成的复现】，能够说明【机制与边界】；不能把它算作独立开发成果。”

AI辅助也应划清责任：如实说明辅助生成或研究的范围，以及本人实际审查、运行和修改了什么，不把生成代码量当作个人工程判断证明。

## 面试前需填写的贡献卡

- 我亲自负责：________；协作/辅助部分：________。
- 一个真实问题的输入与现象：________。
- 我最初的判断及否定它的证据：________。
- 我采取的动作、文件/提交：________。
- 验证方式与结果（不是估计值）：________。
- 当前仍未解决的问题：________。

先填两张卡：一张AI可靠性、一张后端事务或生命周期。未填好的案例只用于解释技术，不用于回答“你最困难的一次经历”。
