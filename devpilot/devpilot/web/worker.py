"""Isolated workbench execution process."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from devpilot.application.bootstrap import initialize_components
from devpilot.domain.task import DevelopmentTask
from devpilot.evals.runner import EvalRunner
from devpilot.security import redact
from devpilot.web.server import read_json, save, workbench_settings


async def execute(path):
    # Parent publishes the process identity before the worker writes job state.
    for _ in range(100):
        job = read_json(path)
        if job.get("pid"):
            break
        await asyncio.sleep(0.05)
    settings = workbench_settings()
    job.update(status="running")
    save(path, job)

    def event(kind, data):
        if kind == "run_started":
            job["run_id"] = data["run_id"]
            save(path, job)
        record = {"event": kind, "data": data, "timestamp": datetime.now(UTC).isoformat()}
        with path.with_suffix(".events.jsonl").open("a", encoding="utf-8") as out:
            out.write(redact(json.dumps(record, ensure_ascii=False), (settings.api_key,)) + "\n")

    try:
        if job["mode"] == "real" and job["task"]["id"].startswith("DEV-"):
            evaluator = EvalRunner(settings=settings, runner_factory=initialize_components)
            result = await evaluator.run_eval(job["task"]["id"], on_event=event)
            job.update(
                status="completed" if result.task_success else "failed",
                error=None if result.task_success else (result.error or result.evaluation_reason),
            )
        else:
            runner = initialize_components(
                settings=settings, fake=job["mode"] == "smoke", on_event=event
            )
            result = await runner.run(DevelopmentTask.model_validate(job["task"]))
            job.update(status=result.status, error=result.error)
    except Exception as exc:
        job.update(status="failed", error=redact(str(exc), (settings.api_key,)))
    job["finished_at"] = datetime.now(UTC).isoformat()
    save(path, job)


if __name__ == "__main__":
    asyncio.run(execute(Path(sys.argv[1])))
