import json, time
from pathlib import Path
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8765", timeout=120)
records = []
for issue in ["DEV-001", "DEV-002"]:
    response = client.post("/api/jobs", json={"issue_id": issue})
    response.raise_for_status()
    job = response.json()
    jid = job["job_id"]
    print(issue, jid, flush=True)
    while True:
        job = client.get("/api/jobs/" + jid).json()
        if job["status"] not in ["running", "queued"]:
            break
        time.sleep(2)
    record = {
        "issue": issue,
        "job_id": jid,
        "run_id": job.get("run_id"),
        "status": job["status"],
        "evaluation": job.get("evaluation"),
        "error": job.get("error"),
    }
    records.append(record)
    Path("runs/workbench-real-validation.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(issue, job["status"], job.get("run_id"), flush=True)
    if job.get("error") and any(
        x in job["error"] for x in ["401", "403", "invalid_api_key", "model_not_found"]
    ):
        print(
            "Provider configuration rejected; remaining task not retried.", flush=True
        )
        break
    if issue == "DEV-001":
        comparison = client.post("/api/jobs/" + jid + "/compare")
        print("business comparison HTTP", comparison.status_code, flush=True)
