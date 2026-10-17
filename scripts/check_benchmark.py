"""Portable entry point for the deterministic dataset gate in CI."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
target_python = repo / "shopflow-order-service/.venv" / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python"
)
output = repo / "runs" / f"benchmark-{uuid.uuid4().hex}"
subprocess.run([
    sys.executable, "-m", "devpilot.cli", "benchmark-check", "--test-python", str(target_python),
    "--output", str(output),
], check=True)
print(f"Benchmark evidence: {output / 'summary.json'}")
