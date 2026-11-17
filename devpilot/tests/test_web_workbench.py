import os
import sys
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from devpilot.settings import Settings
from devpilot.web.server import create_app, save


def target_python():
    root = Path(__file__).resolve().parents[2] / "shopflow-order-service/.venv"
    path = root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not path.is_file():
        pytest.skip("ShopFlow environment is required for application probes")
    return str(path)


def client_for(tmp_path):
    settings = Settings(
        _env_file=None,
        api_key="",
        runs_root=str(tmp_path / "runs"),
        workspace_root=str(tmp_path / "workspaces"),
    )
    return TestClient(create_app(settings)), tmp_path / "runs" / "web-jobs"


def test_environment_and_validation(tmp_path):
    client, jobs = client_for(tmp_path)
    assert client.get("/api/environment").json()["configured"] is False
    assert len(client.get("/api/tasks").json()) == 8
    assert client.post("/api/jobs", json={"issue_id": "DEV-001"}).status_code == 400
    assert client.get("/api/jobs/invalid").status_code == 404
    assert client.get("/api/tasks", headers={"host": "evil.example"}).status_code == 403
    assert (
        client.post(
            "/api/jobs", json={"smoke": True}, headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_pending_job_without_run_id_and_admission(tmp_path):
    client, jobs = client_for(tmp_path)
    jid = "a" * 32
    save(
        jobs / (jid + ".json"),
        {
            "job_id": jid,
            "status": "queued",
            "pid": os.getpid(),
            "process_started": psutil.Process().create_time(),
            "created_at": "2026",
            "run_id": None,
        },
    )
    assert client.get("/api/jobs/" + jid).status_code == 200
    assert client.get("/api/jobs/" + jid + "/diff").json() == {"diff": ""}
    assert client.post("/api/jobs", json={"smoke": True}).status_code == 409


def test_dead_worker_and_partial_event(tmp_path):
    client, jobs = client_for(tmp_path)
    jid = "b" * 32
    save(
        jobs / (jid + ".json"),
        {
            "job_id": jid,
            "status": "running",
            "pid": os.getpid(),
            "process_started": 0,
            "created_at": "2026",
            "run_id": None,
        },
    )
    (jobs / (jid + ".events.jsonl")).write_text('{"event":"first"}\n{"event":', encoding="utf-8")
    assert client.get("/api/jobs/" + jid).json()["status"] == "interrupted"
    assert client.get("/api/jobs/" + jid + "/events").json() == {
        "events": [{"event": "first"}],
        "cursor": 1,
    }
    assert client.get("/api/jobs/" + jid + "/events?cursor=1").json()["events"] == []


def test_probe_rejects_defect_and_accepts_reference(tmp_path):
    from devpilot.evals.benchmark import apply_dataset_patch, packaged_baseline, prepare_task
    from devpilot.web.compare import probe

    repo = tmp_path / "before"
    prepare_task(packaged_baseline(), repo, "DEV-001")
    python = target_python()
    before = probe(repo, python, tmp_path / "before.json")
    assert [c["passed"] for c in before["cases"]] == [False, False, True]
    apply_dataset_patch(repo, "DEV-001", "reference")
    # Probe creates its own data; remove only the database from this pytest temp repo.
    (repo / "shopflow.db").unlink()
    after = probe(repo, python, tmp_path / "after.json")
    assert all(c["passed"] for c in after["cases"])


def test_legacy_provenance_and_trace(tmp_path):
    root = tmp_path / "runs" / "run_12345678"
    root.mkdir(parents=True)
    save(root / "result.json", {"status": "completed"})
    save(root / "state.json", {"task": {"id": "DEV-001", "title": "Old run"}})
    (root / "trace.jsonl").write_text('{"event":"run_completed"}\n', encoding="utf-8")
    client, _ = client_for(tmp_path)
    job = client.get("/api/jobs").json()[0]
    assert job["mode"] == "unknown"
    assert job["model"] == "未知（旧记录）"
    assert (
        client.get("/api/jobs/" + job["job_id"] + "/events").json()["events"][0]["event"]
        == "run_completed"
    )
    assert client.post("/api/jobs/" + job["job_id"] + "/compare").status_code == 400


def test_comparison_evidence_is_bound_and_original_unchanged(tmp_path):
    from devpilot.evals.benchmark import apply_dataset_patch, packaged_baseline, prepare_task
    from devpilot.web.compare import compare_run
    from devpilot.web.server import read_json

    run_id = "run_12345678"
    workspace = tmp_path / "workspaces" / run_id / "repo"
    prepare_task(packaged_baseline(), workspace, "DEV-001")
    apply_dataset_patch(workspace, "DEV-001", "reference")
    original = {
        "acceptance_coverage": [{"criterion": str(i), "status": "uncovered"} for i in range(4)]
    }
    output = tmp_path / "runs" / run_id
    output.mkdir(parents=True)
    save(output / "result.json", original)
    python = target_python()
    settings = Settings(
        _env_file=None,
        runs_root=str(tmp_path / "runs"),
        workspace_root=str(tmp_path / "workspaces"),
        test_python=python,
    )
    result = compare_run({"run_id": run_id}, settings)
    assert len(result["candidate_sha256"]) == 64
    assert [x["status"] for x in result["acceptance_coverage"]] == ["verified"] * 3 + ["uncovered"]
    assert read_json(output / "result.json") == original
    assert read_json(output / "comparison.json") == result
    assert not (workspace / "shopflow.db").exists()


def test_api_worker_smoke_end_to_end(tmp_path):
    import time

    client, _ = client_for(tmp_path)
    response = client.post("/api/jobs", json={"smoke": True})
    assert response.status_code == 202
    jid = response.json()["job_id"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        job = client.get("/api/jobs/" + jid).json()
        if job["status"] not in {"queued", "running"}:
            break
        time.sleep(0.2)
    assert job["status"] == "completed", job.get("error")
    assert job["mode"] == "smoke"
    assert job["task"]["id"] == "SMOKE"
    assert job["result"]["status"] == "completed"
    assert "calculator.py" in client.get("/api/jobs/" + jid + "/diff").json()["diff"]
    events = client.get("/api/jobs/" + jid + "/events").json()["events"]
    assert any(e["event"] == "tool_result" and e["data"].get("success") is False for e in events)
    assert events[-1]["event"] == "run_completed"


@pytest.mark.asyncio
async def test_successful_evaluation_reason_is_not_error(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from devpilot.web import worker

    path = tmp_path / "job.json"
    save(path, {"pid": os.getpid(), "mode": "real", "task": {"id": "DEV-002"}})

    class SuccessfulEvaluator:
        def __init__(self, **kwargs):
            pass

        async def run_eval(self, *args, **kwargs):
            return SimpleNamespace(
                task_success=True, error=None, evaluation_reason="9 passed, 0 failed"
            )

    monkeypatch.setattr(worker, "EvalRunner", SuccessfulEvaluator)
    monkeypatch.setattr(worker, "workbench_settings", lambda: Settings(_env_file=None, api_key=""))
    await worker.execute(path)
    result = worker.read_json(path)
    assert result["status"] == "completed"
    assert result["error"] is None
