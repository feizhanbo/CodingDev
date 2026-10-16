# Codex 与 GitHub 本地迭代

## 2026-10-16 提交准备更新

- 已按用户的推送要求整理当前改动，目标分支为 `codex/devpilot-eval-hardening`。
- 已修复 `test_returns_all_fields` 的预期字段集合，保留完整字段断言并纳入新增的四个 LLM 指标。
- 修复后的 tracing 测试：28 passed；两个项目的 Ruff 和 `git diff --check` 均通过。此次没有重跑全量测试，下文全量结果是 2026-09-30 的历史记录。
- 已重新获取远程，提交前本地 `main` 与 `origin/main` 仍一致；GitHub CLI 认证及 `workflow` 权限有效。
- 非忽略文件的常见凭据模式扫描通过，`devpilot/.env` 仍被 Git 忽略。
- 暂存区空白检查排除 benchmark 的 `.patch` 数据文件：其中空白上下文行的单个空格是 unified diff 格式的一部分，需保留；其余暂存文件检查通过。

## 本机连接检查（2026-09-30）

- 仓库：`https://github.com/feizhanbo/CodingDev.git`（公开仓库）。
- 本地 `main` 与远程 `main` 均为 `1ee0adf0549a807e1b99705c027742c48d634292`，获取远程后 ahead / behind 为 `0 / 0`。
- 已安装 Git `2.50.0.windows.1`、GitHub CLI `2.97.0`、Git Credential Manager `2.6.1`，不需要重复安装。
- GitHub CLI 在正常 Windows 用户环境中已登录 `feizhanbo`，仓库 API 确认有 push 权限。
- 已完成设备授权，确认令牌含 `repo` 和 `workflow`；GitHub CLI 的 github.com Git 协议已统一为 HTTPS。
- 已运行 `gh auth setup-git --hostname github.com`，在用户 Git 配置中为 GitHub 配置 CLI 凭据助手。令牌保留在系统凭据存储中。
- Git 直连 GitHub 超时或连接被重置；已验证现有 Windows 代理，并仅在当前仓库设置 `http.https://github.com/.proxy=http://127.0.0.1:7897`。
- `git fetch origin --prune` 成功。
- `git push --dry-run origin HEAD:refs/heads/codex/connection-check` 成功。此命令没有创建远程分支或上传工作区改动；不保证分支保护、工作流权限等服务端规则允许任意后续提交。

## 当前未提交差异

本任务开始时：43 个修改文件、20 个删除文件、59 个新增文件（新增文件按文件展开计数）。这些是工作区差异，不是尚未推送的提交。本说明文件不包含在上述初始计数中。

| 范围 | 主要变化 |
| --- | --- |
| 评测资源 | `devpilot/evals` 迁入 `devpilot/devpilot/evals`，加入 benchmark manifest、起始/参考补丁，扩充隐藏测试与资源校验 |
| 验证机制 | 新增冻结基线与证据快照，独立测试候选代码，校验测试完整性与新增回归测试 |
| Runtime / LLM | 每次运行重置状态，增加请求级指标、重试记录及运行产物 |
| 配置和 CLI | 新增统一 Settings，调整 CLI、测试解释器和超时设置 |
| 工程化 | 新增双平台 GitHub Actions、benchmark/wheel 检查脚本，调整开发脚本、Python 版本和文档 |
| 回归测试 | 适配评测包迁移，新增配置、证据、benchmark 等测试 |

检查发现 `.env.example` 含疑似真实密钥，已把原配置保存在被 Git 忽略的 `devpilot/.env`，并将示例密钥恢复为占位符。建议到密钥提供方更换该密钥。常见凭据模式扫描未在其他受跟踪或非忽略文件中发现匹配；此扫描不能证明不存在任何形式的秘密。

## 本次验证结果

- 两个项目的 Ruff 检查均通过；`git diff --check` 通过。
- ShopFlow：50 passed。
- DevPilot：439 passed、1 failed、1 skipped、1 xfailed（322.71 秒）。
- 失败位置：`devpilot/tests/tracing/test_metrics.py:124`。`MetricsCollector.to_dict()` 新增 `known_tokens`、`llm_requests`、`llm_latency_ms`、`llm_unknown_usage_requests`，但该测试的预期字段集合仍未更新。需在代码迭代中处理；本任务仅报告，未修改这部分业务代码或测试。
- 本次未执行完整远程 CI、wheel 验证或真实模型评测，不能视为版本验收完成。

## 日常操作

在 Codex 中明确要求“检查改动、验证、提交到指定分支并推送”，即可由 Codex 执行 Git/gh 命令。首次整理当前改动时，先审阅新增资源和目录迁移，再按功能拆分提交。

```powershell
git fetch origin --prune
git status --short --branch
git diff --stat
git diff --check
git switch -c codex/your-change
# 只暂存审阅过的文件，再检查暂存区。
git add <reviewed-paths>
git diff --cached --stat
git commit -m "Describe the change"
git push -u origin HEAD
gh pr create --base main --fill
```

上面是操作示例，本任务没有实际提交或推送业务代码。PR 创建应在用户要求该操作时执行。

## Windows 环境注意事项

- 本任务的 Windows 沙箱中 `gh auth status` 报 token invalid，但在获准的沙箱外执行环境中认证成功。遇到同样情况，先用获准的执行环境核验，不要直接注销账号或把令牌写入文件。
- Codex 的网络操作和 `.git` 写入可能需要应用的命令审批；保持正常权限边界，按具体命令执行，不需要关闭整个沙箱。
- 本机代理需保持运行。端口变化后更新当前仓库代理；不再需要时运行 `git config --local --unset http.https://github.com/.proxy`。
- gh 的 GitHub API 可用并不代表 github.com 网页授权端点可直连。设备授权如超时，可在该 PowerShell 进程中设置 `$env:HTTPS_PROXY='http://127.0.0.1:7897'` 后重试。
- 当前新增 Actions 工作流需要 OAuth `workflow` 权限。本次已通过 `gh auth refresh --hostname github.com --scopes workflow` 完成官方设备授权并核验权限；更换账号或令牌后需重新检查。
- `uv` 默认缓存目录在沙箱外，本次通过虚拟环境中的解释器与 Ruff 执行检查；也可以在获准环境运行 `dev.ps1`。

参考：[GitHub CLI 凭据助手](https://cli.github.com/manual/gh_auth_setup-git)、[OpenAI Windows 沙箱说明](https://learn.chatgpt.com/docs/windows/windows-sandbox)。
