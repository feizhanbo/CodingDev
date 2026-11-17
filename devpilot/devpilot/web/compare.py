"""Compare immutable copies of actual starting and candidate code."""

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from devpilot.evals.benchmark import packaged_baseline, prepare_task
from devpilot.security import process_environment, redact
from devpilot.verification.evidence import inventory
from devpilot.web.server import read_json, save


def probe(repo, python, output):
    try:
        result = subprocess.run(
            [python, str(Path(__file__).with_name("probe.py")), str(repo), str(output)],
            cwd=repo,
            env=process_environment(),
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode or not output.exists():
            return {"error": (result.stderr or result.stdout)[-4000:]}
        return {"cases": json.loads(output.read_text(encoding="utf-8"))}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}


def compare_run(job, settings):
    workspace = Path(settings.workspace_root).resolve() / job["run_id"] / "repo"
    if not workspace.is_dir():
        raise ValueError("Candidate workspace is missing")
    with tempfile.TemporaryDirectory(prefix="devpilot-compare-") as folder:
        root = Path(folder)
        before = root / "before"
        after = root / "after"
        starting_point = prepare_task(packaged_baseline(), before, "DEV-001")
        after.mkdir()
        hashes = inventory(workspace)
        for relative, expected in hashes.items():
            source = workspace / relative
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Candidate changed while snapshotting")
            target = after / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        result = {
            "run_id": job["run_id"],
            "starting_point": starting_point,
            "created_at": datetime.now(UTC).isoformat(),
            "candidate_sha256": hashlib.sha256(
                json.dumps(hashes, sort_keys=True).encode()
            ).hexdigest(),
            "before": probe(before, settings.test_python, root / "before.json"),
            "after": probe(after, settings.test_python, root / "after.json"),
        }
        original = read_json(Path(settings.runs_root) / job["run_id"] / "result.json")
        coverage = original.get("acceptance_coverage") or [
            {"criterion": criterion, "status": "uncovered", "checks": []}
            for criterion in job.get("task", {}).get("acceptance_criteria", [])
        ]
        cases = result["after"].get("cases", [])
        before_cases = result["before"].get("cases", [])
        if len(cases) == 3 and len(before_cases) == 3:
            cases[2]["passed"] = cases[2]["passed"] and cases[2]["body"] == before_cases[2]["body"]
        result["acceptance_coverage"] = [
            dict(
                item,
                status=("verified" if cases[i]["passed"] else "failed"),
                checks=["business_probe"],
                evidence_refs=["comparison.json"],
            )
            if i < 3 and len(cases) == 3
            else item
            for i, item in enumerate(coverage)
        ]
        result = json.loads(redact(json.dumps(result), (settings.api_key,)))
        save(Path(settings.runs_root) / job["run_id"] / "comparison.json", result)
        return result
