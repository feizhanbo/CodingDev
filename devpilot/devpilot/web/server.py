"""Local workbench API; worker processes own execution, files own evidence."""

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from devpilot.application.bootstrap import load_issue
from devpilot.evals.benchmark import resource_root
from devpilot.security import redact
from devpilot.settings import Settings
from devpilot.storage import RunLock, atomic_write

ROOT = Path(__file__).resolve().parents[2]


def read_json(path):
    try:
        if path.resolve() != path.absolute():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2))


class StartRequest(BaseModel):
    issue_id: str | None = None
    smoke: bool = False
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=12000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)


def workbench_settings():
    settings = Settings(_env_file=ROOT / ".env")
    target = ROOT.parent / "shopflow-order-service" / ".venv"
    python = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if settings.test_python == sys.executable and python.is_file():
        settings = settings.model_copy(update={"test_python": str(python)})
    return settings


def create_app(settings=None):
    settings = settings or workbench_settings()
    runs = Path(settings.runs_root).resolve()
    jobs = runs / "web-jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    # Index historical artifacts as unknown provenance, never infer real-model success.
    indexed_runs = {read_json(p).get("run_id") for p in jobs.glob("*.json")}
    for result_path in runs.glob("run_*/result.json"):
        rid = result_path.parent.name
        jid = hashlib.md5(rid.encode(), usedforsecurity=False).hexdigest()
        if rid in indexed_runs:
            continue
        result = read_json(result_path)
        state = read_json(result_path.with_name("state.json"))
        if not state.get("task"):
            continue
        save(
            jobs / (jid + ".json"),
            {
                "job_id": jid,
                "run_id": rid,
                "status": result.get("status", "interrupted"),
                "mode": "unknown",
                "model": "未知（旧记录）",
                "revision": "unknown",
                "task": state["task"],
                "created_at": datetime.fromtimestamp(result_path.stat().st_mtime, UTC).isoformat(),
                "legacy": True,
            },
        )
    app = FastAPI(title="DevPilot Workbench")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "testserver"}:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Local host required"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {
            f"http://{request.headers.get('host')}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }:
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Origin rejected"}, status_code=403)
        return await call_next(request)

    def job_path(job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise HTTPException(404, "Unknown job")
        return jobs / (job_id + ".json")

    def get_job(job_id):
        path = job_path(job_id)
        job = read_json(path)
        if not job:
            raise HTTPException(404, "Unknown job")
        if job["status"] in {"queued", "running"}:
            try:
                process = psutil.Process(job["pid"])
                alive = abs(process.create_time() - job["process_started"]) < 1
            except (psutil.Error, KeyError):
                alive = False
            if not alive:
                job = read_json(path)
                if job["status"] in {"queued", "running"}:
                    job.update(
                        status="interrupted", error="执行进程已退出；保留已有证据，不自动重放"
                    )
                    save(path, job)
        return job

    def artifact(job, name):
        run_id = job.get("run_id") or ""
        if not re.fullmatch(r"run_[0-9a-f]{8}", run_id):
            return None
        path = runs / run_id / name
        if path.resolve() != path.absolute() or not path.is_file():
            return None
        return path

    @app.get("/api/environment")
    def environment():
        return {
            "model": settings.model,
            "configured": bool(settings.api_key),
            "endpoint_configured": bool(settings.base_url),
            "max_steps": settings.max_steps,
            "max_run_seconds": settings.max_run_seconds,
            "repository": "ShopFlow",
            "runtime": "Custom Runtime",
        }

    @app.get("/api/tasks")
    def tasks():
        return [
            load_issue(str(p)).model_dump()
            for p in sorted((resource_root() / "issues").glob("*.yaml"))
        ]

    @app.get("/api/jobs")
    def list_jobs():
        return sorted(
            [get_job(p.stem) for p in jobs.glob("*.json")],
            key=lambda j: j["created_at"],
            reverse=True,
        )

    @app.post("/api/jobs", status_code=202)
    def start(body: StartRequest):
        if not body.smoke and not settings.api_key:
            raise HTTPException(400, "请先在服务端 .env 中配置模型 API Key")
        if body.issue_id and body.issue_id not in {t["id"] for t in tasks()}:
            raise HTTPException(400, "Unknown preset task")
        if (
            not body.smoke
            and not body.issue_id
            and (
                not body.title.strip()
                or not body.description.strip()
                or not body.acceptance_criteria
                or any(not x.strip() or len(x) > 2000 for x in body.acceptance_criteria)
            )
        ):
            raise HTTPException(400, "请填写标题、描述与逐条验收条件")
        try:
            with RunLock(jobs / ".admission.lock"):
                if any(j["status"] in {"running", "queued"} for j in list_jobs()):
                    raise HTTPException(409, "已有任务正在执行")
                jid = uuid.uuid4().hex
                task = (
                    {
                        "id": "SMOKE",
                        "title": "流程自检：计算器修复",
                        "description": "修复内置加法样例",
                        "acceptance_criteria": ["新增测试"],
                        "constraints": [],
                    }
                    if body.smoke
                    else next((t for t in tasks() if t["id"] == body.issue_id), None)
                )
                task = task or {
                    "id": "CUSTOM-" + jid[:8],
                    "title": body.title,
                    "description": body.description,
                    "acceptance_criteria": body.acceptance_criteria,
                    "constraints": [],
                }
                revision = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
                ).stdout.strip()
                job = {
                    "job_id": jid,
                    "status": "queued",
                    "mode": "smoke" if body.smoke else "real",
                    "task": task,
                    "model": settings.model if not body.smoke else "FakeLLM",
                    "revision": revision,
                    "source_sha256": hashlib.sha256(
                        b"".join(
                            p.relative_to(ROOT).as_posix().encode() + p.read_bytes()
                            for p in sorted((ROOT / "devpilot").rglob("*.py"))
                        )
                    ).hexdigest(),
                    "created_at": datetime.now(UTC).isoformat(),
                    "run_id": None,
                }
                save(job_path(jid), job)
                worker_env = {k: v for k, v in os.environ.items() if not k.startswith("DEVPILOT_")}
                worker_env.update(
                    {
                        "DEVPILOT_" + k.upper(): str(v)
                        for k, v in settings.model_dump().items()
                        if v is not None
                    }
                )
                for key in ("runs_root", "workspace_root", "base_repo"):
                    worker_env["DEVPILOT_" + key.upper()] = str(
                        Path(getattr(settings, key)).resolve()
                    )
                with (jobs / (jid + ".log")).open("w", encoding="utf-8") as log:
                    proc = subprocess.Popen(
                        [sys.executable, "-m", "devpilot.web.worker", str(job_path(jid))],
                        cwd=ROOT,
                        env=worker_env,
                        stdout=log,
                        stderr=log,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                job.update(pid=proc.pid, process_started=psutil.Process(proc.pid).create_time())
                save(job_path(jid), job)
                return job
        except BlockingIOError as exc:
            raise HTTPException(409, "任务启动中") from exc

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str):
        job = get_job(job_id)
        for name, file in [
            ("result", "result.json"),
            ("evaluation", "eval_result.json"),
            ("requests", "llm-requests.json"),
            ("comparison", "comparison.json"),
        ]:
            p = artifact(job, file)
            job[name] = read_json(p) if p else None
        return json.loads(redact(json.dumps(job), (settings.api_key,)))

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, cursor: int = 0):
        get_job(job_id)
        p = jobs / (job_id + ".events.jsonl")
        values = []
        if not p.is_file():
            legacy_path = artifact(get_job(job_id), "trace.jsonl")
            if legacy_path:
                p = legacy_path
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    values.append(json.loads(line))
                except ValueError:
                    break
        cursor = max(0, cursor)
        return {"events": values[cursor : cursor + 500], "cursor": min(len(values), cursor + 500)}

    @app.get("/api/jobs/{job_id}/diff")
    def diff(job_id: str):
        p = artifact(get_job(job_id), "final.diff")
        return {"diff": redact(p.read_text(encoding="utf-8") if p else "", (settings.api_key,))}

    @app.post("/api/jobs/{job_id}/compare")
    def compare(job_id: str):
        job = get_job(job_id)
        if (
            job["mode"] != "real"
            or job["task"]["id"] != "DEV-001"
            or job["status"] not in {"completed", "failed"}
            or not job.get("run_id")
        ):
            raise HTTPException(400, "仅支持已结束的真实 DEV-001 运行")
        from devpilot.web.compare import compare_run

        try:
            return compare_run(job, settings)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, redact(str(exc), (settings.api_key,))) from exc

    dist = ROOT.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


def main():
    import os

    import uvicorn

    os.chdir(ROOT)
    uvicorn.run(create_app(), host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
