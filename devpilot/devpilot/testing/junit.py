import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel, Field


class SuiteResult(BaseModel):
    status: str
    collected: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    assertion_failures: int = 0
    duration_ms: int = 0
    node_outcomes: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None
    report_file: str | None = None
    log_file: str | None = None


def parse_junit(path: Path, exit_code: int, max_bytes: int = 2097152) -> SuiteResult:
    """A zero exit status without meaningful, valid test evidence is not PASS."""
    if not path.is_file():
        return SuiteResult(status="ERROR", reason="Missing structured test report")
    if path.stat().st_size > max_bytes:
        return SuiteResult(status="ERROR", reason="Structured test report exceeds output limit")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return SuiteResult(status="ERROR", reason=f"Invalid structured test report: {exc}")
    result = SuiteResult(status="ERROR", report_file=str(path))
    for case in root.iter("testcase"):
        result.collected += 1
        key = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("error") is not None:
            result.errors += 1
            outcome = "ERROR"
        elif case.find("failure") is not None:
            result.failed += 1
            failure = case.find("failure")
            details = (failure.get("message", "") or "") + (failure.text or "")
            if "AssertionError" in details or "assert " in details:
                result.assertion_failures += 1
            outcome = "FAIL"
        elif case.find("skipped") is not None:
            result.skipped += 1
            outcome = "SKIP"
        else:
            result.passed += 1
            outcome = "PASS"
        # Duplicate node identities make cross-run regression statistics ambiguous.
        if key in result.node_outcomes:
            result.reason = "Duplicate test identity in report"
            return result
        result.node_outcomes[key] = outcome
    if result.errors or exit_code not in (0, 1):
        result.reason = f"Test execution/collection error (exit {exit_code})"
    elif result.collected == 0 or result.passed + result.failed == 0:
        result.reason = "No executed tests (empty or all skipped)"
    elif result.failed:
        result.status = "FAIL"
    elif exit_code == 0:
        result.status = "PASS"
    else:
        result.reason = "Process exit disagrees with structured report"
    return result
