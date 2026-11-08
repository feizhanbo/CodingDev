"""Offline paired runtime measurements; run after other test processes finish.

Use devpilot/.venv/Scripts/python.exe scripts/compare_runtime_overhead.py.
Each sample uses a fresh process and run directory. Imports are excluded from
the measured execution interval; process startup is reported separately.
"""

import argparse
import asyncio
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def sample(backend, directory):
    sys.path.insert(0, str(ROOT / "devpilot"))
    from devpilot.application.factory import create_runtime
    from devpilot.domain.task import DevelopmentTask
    from devpilot.runtime.contracts import RunRequest
    from devpilot.runtime.langgraph.runner import LangGraphAgentRunner  # noqa: F401
    from devpilot.settings import Settings

    started = time.perf_counter()
    runtime = create_runtime(fake=True, settings=Settings(
        _env_file=None, runtime=backend, llm_backend="openai",
        workspace_root=str(directory / "workspaces"), runs_root=str(directory / "runs"),
    ))
    outcome = await runtime.execute(RunRequest(DevelopmentTask(
        id="OVERHEAD", title="Fix addition", description="Fix addition",
        acceptance_criteria=["Addition is correct", "Add tests"],
    )))
    elapsed = time.perf_counter() - started
    result = outcome.result
    if result.status != "completed":
        raise RuntimeError(result.model_dump_json())
    return {
        "backend": backend, "elapsed_seconds": elapsed,
        "artifact_bytes": sum(p.stat().st_size for p in Path(outcome.artifacts).rglob("*")
                              if p.is_file()),
        "contract": {"status": result.status, "steps": result.total_steps,
                     "requests": result.budget["llm_requests"],
                     "observations": [o.name for o in result.observations],
                     "diff_sha256": hashlib.sha256(outcome.final_diff.encode()).hexdigest()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "p5-overhead")
    parser.add_argument("--worker", choices=["custom", "langgraph"])
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(asyncio.run(sample(args.worker, args.output.resolve()))))
        return
    if args.pairs < 10:
        parser.error("Acceptance measurements require at least ten pairs")
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for pair in range(args.pairs):
        order = ["custom", "langgraph"] if pair % 2 == 0 else ["langgraph", "custom"]
        current = {}
        for backend in order:
            directory = args.output / f"pair-{pair:02d}-{backend}"
            started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", backend,
                 "--output", str(directory.resolve())],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=900,
                check=False,
            )
            (args.output / f"pair-{pair:02d}-{backend}.log").write_text(
                completed.stderr, encoding="utf-8",
            )
            completed.check_returncode()
            record = json.loads(completed.stdout.strip().splitlines()[-1])
            record.update(pair=pair, process_seconds=time.perf_counter() - started)
            current[backend] = record
            records.append(record)
            (args.output / "samples.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        if current["custom"]["contract"] != current["langgraph"]["contract"]:
            raise AssertionError(f"Runtime contract mismatch in pair {pair}")
        print(f"Pair {pair + 1}/{args.pairs} completed", flush=True)
    medians = {backend: statistics.median(r["elapsed_seconds"] for r in records
                                        if r["backend"] == backend)
               for backend in ("custom", "langgraph")}
    summary = {"pairs": args.pairs, "median_seconds": medians,
               "median_overhead_ratio": medians["langgraph"] / medians["custom"] - 1,
               "scope": "fake model; execution interval excludes imports; fresh process per sample"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
