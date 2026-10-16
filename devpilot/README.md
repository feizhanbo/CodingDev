# DevPilot V1

Enterprise development task agent: Issue → Code → Test → Repair → Verify → Report

## Overview

DevPilot is an AI agent system that receives a development issue, explores the target codebase, creates an implementation plan, makes code changes, runs tests, self-repairs on failure, and outputs a Git diff with delivery report.

V1 Mode: Single Agent + Local Sandbox + Mock Backend (ShopFlow) + Deterministic Verifier

## Quick Start

### Prerequisites

- Python 3.12+
- uv (package manager)
- git
- ripgrep (for code search)

### Install

```bash
cd devpilot
uv sync
```

### ShopFlow Setup

```bash
cd shopflow-order-service
uv sync
uv run python -m app.db.seed  # Initialize sample data
```

### Run an Issue

```bash
# With real LLM (requires OPENAI_API_KEY)
cp .env.example .env  # Edit and add your API key
uv run python -m devpilot.cli run devpilot/evals/issues/DEV-001.yaml

# With FakeLLMClient (no API key needed)
uv run python -m devpilot.cli run devpilot/evals/issues/DEV-001.yaml --fake
```

### Run Evaluation

```bash
# Single issue
uv run python -m devpilot.cli eval DEV-001 --fake

# All issues
uv run python -m devpilot.cli eval --all --fake
```

### Inspect Results

```bash
# View run details
uv run python -m devpilot.cli inspect <run-id>

# View diff
uv run python -m devpilot.cli diff <run-id>
```

## Architecture

```
DevPilot CLI
    │
    ▼
Agent Runtime (Custom)
  Loop │ State Manager │ Context Builder │ Guardrails
    │
    ▼
DeveloperAgent
    │ LLM decision / tool call
    ▼
Tool Registry (8 tools)
  repo.list_files │ repo.search_code │ repo.read_file
  code.apply_patch │ code.create_file
  test.run │ git.diff │ git.status
    │
    ▼
Sandbox Workspace → ShopFlow Git Repository
    │
    ▼
Final Verifier → Diff + Run Report
```

### Key Components

| Component | Responsibility |
|-----------|---------------|
| DeveloperAgent | Makes decisions, calls tools, requests finish |
| AgentRuntime | Control loop, state, guardrails, verifier |
| ToolRegistry | Register and dispatch 8 tools |
| SandboxWorkspace | Isolated workspace from baseline repo |
| TaskVerifier | Deterministic completion verification |
| TraceWriter | JSONL trace recording |
| EvalRunner | Batch evaluation with hidden tests |

### Tool List

| Tool | Purpose |
|------|---------|
| repo.list_files | List files in workspace |
| repo.search_code | Search code with ripgrep |
| repo.read_file | Read file with line numbers |
| code.apply_patch | Apply unified diff |
| code.create_file | Create new file |
| test.run | Run pytest in workspace |
| git.diff | Get git diff |
| git.status | Get git status |

### Issue Dataset

| Issue | Type | Difficulty |
|-------|------|-----------|
| DEV-001 | Feature (order status filter) | ★ |
| DEV-002 | Bug (invalid cancellation) | ★ |
| DEV-003 | Bug (pagination edge) | ★★ |
| DEV-004 | Bug (coupon calculation) | ★★ |
| DEV-005 | Performance (N+1 query) | ★★★ |
| DEV-006 | Feature (email normalization) | ★★ |
| DEV-007 | Bug (duplicate payment) | ★★★ |
| DEV-008 | Feature (audit fields) | ★★★ |

## Testing

```bash
# DevPilot tests
cd devpilot
uv run pytest

# ShopFlow tests
cd shopflow-order-service
uv run pytest

# Both (from root)
.\dev.ps1 test
```

## Configuration

See `.env.example` for all configuration options.

## Known Limitations

- V1 uses Custom Runtime (not LangGraph/OpenAI Agents SDK)
- No Git commit/push (manual review required)
- No GitHub/Jira integration
- No Multi-Agent
- No network access (sandboxed)
- No production deployment (local experiment)
- No long-term memory
- No Web UI (CLI only)

## Project Structure

```
devpilot/
├── devpilot/
│   ├── domain/          # Domain models (Task, State, Plan, Decision)
│   ├── agents/          # DeveloperAgent
│   ├── runtime/         # AgentRunner, StateManager, LoopGuard, ContextBuilder
│   ├── tools/           # 8 tools + PathGuard + Registry
│   ├── workspace/       # SandboxWorkspace
│   ├── verification/    # TaskVerifier
│   ├── llm/             # LLMClient, OpenAI, Fake, prompts
│   ├── tracing/         # TraceWriter, TraceEvent
│   └── cli.py           # CLI (run, inspect, diff, eval)
├── evals/
│   ├── runner.py        # EvalRunner
│   ├── metrics.py       # Metrics collection
│   ├── issues/          # DEV-001~008 YAML
│   └── hidden_tests/    # Hidden tests
├── tests/               # Unit + Integration + E2E tests
└── pyproject.toml
```

## Future Roadmap

- V1.1: Context compaction + Better planning
- V1.2: Eval dashboard + regression benchmark
- V2: GitHub Issue → Branch → PR + Human approval
- V3: Project knowledge / RAG
- V4: Review Agent
- V5: Framework Runtime (LangGraph) + durable state
- V6: Multi-Agent R&D Supervisor
- V7: SRE Agent

## V1 hardening configuration

Python 3.12 is pinned for development. `run` and `eval` use the same Settings: explicit arguments override environment variables, which override the chosen `.env`, then defaults. Use `--env-file PATH` to select the dotenv file. Existing `DEVPILOT_*` names remain supported.

The target test interpreter must include the target repository dependencies. On Windows, after `uv sync --frozen` in both projects, run from this directory:

```powershell
uv run devpilot run devpilot/evals/issues/DEV-001.yaml --test-python ../shopflow-order-service/.venv/Scripts/python.exe
```

On POSIX use `../shopflow-order-service/.venv/bin/python`. The equivalent environment variable is `DEVPILOT_TEST_PYTHON`. Runtime step/retry/file/patch limits and the test timeout are shared by run and eval.

Evaluation code and resources now live in `devpilot.evals` and ship in the wheel. `eval` resolves default issues from package resources; `--issues-dir` and `--hidden-tests-dir` override them. Python callers should import `devpilot.evals.runner`, replacing `evals.runner`. `inspect` and `diff` use `DEVPILOT_RUNS_ROOT`, and diff fallback uses `DEVPILOT_WORKSPACE_ROOT`. Each test invocation gets its own log under the run artifact directory.

Hardening is in progress. The current local subprocess backend does not enforce network isolation; the network setting is not yet an isolation guarantee. Fake evaluation still requires the planned smoke/capability separation and must not be interpreted as Agent capability evidence. See `../docs/v1-hardening-progress.md` for verified work and remaining gates.
