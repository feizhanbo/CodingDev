"""Parse pytest output to extract structured test failure information."""

from __future__ import annotations

import re
from typing import Any

# Pytest verbose summary line, e.g.
#   FAILED tests/api/test_orders.py::test_filter_orders_by_status
_FAILED_RE = re.compile(r"FAILED\s+(.+?)(?:\s|$)")

# Pytest failure section header, e.g.  _____ test_name _____
_FAIL_HEADER_RE = re.compile(r"_{5,}\s+(.+?)\s+_{5,}")

# Final exception line in a short traceback, e.g.
#   E   TypeError: list_orders() got an unexpected keyword argument 'status'
_EXC_RE = re.compile(
    r"^E\s+(\w+(?:Error|Exception)):\s*(.+)", re.MULTILINE
)

# Bare assertion line in a short traceback, e.g.  E   assert 1 == 2
_ASSERT_RE = re.compile(r"^E\s+(assert\s.+)$", re.MULTILINE)

# Long-traceback file references:  File "app/x.py", line 45, in f
_FILE_LONG_RE = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)')

# Short-traceback file references:  app/services/order_service.py:45: in list_orders
_FILE_SHORT_RE = re.compile(
    r"^(\s*)(\S[^:\n]*?\.py):(\d+):\s+in\s", re.MULTILINE
)


def parse_test_failures(stdout: str, stderr: str = "") -> dict[str, Any]:
    """Parse pytest output to extract structured failure info.

    Returns a dict with:
    - kind: "test_failure"
    - failed_tests: list of test node ids / names
    - errors: list of {type, message, locations}
    - summary: brief human-readable summary

    Never raises; always returns a dict with at least ``kind`` and ``summary``.
    """
    text = stdout or ""
    if stderr:
        text = f"{text}\n{stderr}"

    failed_tests: list[str] = []

    for match in _FAILED_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in failed_tests:
            failed_tests.append(name)

    # Fall back to section headers when no FAILED summary lines are present
    # (e.g. truncated output). Skip names already covered by a full node id.
    for match in _FAIL_HEADER_RE.finditer(text):
        name = match.group(1).strip()
        if name and not _is_covered(name, failed_tests):
            failed_tests.append(name)

    errors: list[dict[str, Any]] = []
    seen_errors: set[tuple[str, str]] = set()

    for match in _EXC_RE.finditer(text):
        exc_type = match.group(1)
        message = match.group(2).strip()
        key = (exc_type, message)
        if key in seen_errors:
            continue
        seen_errors.add(key)
        errors.append(
            {
                "type": exc_type,
                "message": message,
                "locations": _extract_traceback_locations(text, match.start()),
            }
        )

    for match in _ASSERT_RE.finditer(text):
        message = match.group(1).strip()
        key = ("AssertionError", message)
        if key in seen_errors:
            continue
        seen_errors.add(key)
        errors.append(
            {
                "type": "AssertionError",
                "message": message,
                "locations": _extract_traceback_locations(text, match.start()),
            }
        )

    if not failed_tests and not errors:
        summary_match = re.search(r"(\d+)\s+failed", text)
        passed_match = re.search(r"(\d+)\s+passed", text)
        if summary_match or passed_match:
            parts = []
            if summary_match:
                parts.append(f"{summary_match.group(1)} failed")
            if passed_match:
                parts.append(f"{passed_match.group(1)} passed")
            return {
                "kind": "test_failure",
                "failed_tests": [],
                "errors": [],
                "summary": ", ".join(parts),
            }
        return {
            "kind": "test_failure",
            "failed_tests": [],
            "errors": [],
            "summary": text[-500:] if text else "No output captured",
        }

    return {
        "kind": "test_failure",
        "failed_tests": failed_tests,
        "errors": errors,
        "summary": f"{len(failed_tests)} test(s) failed",
    }


def _is_covered(name: str, existing: list[str]) -> bool:
    """Return True if *name* is already represented by an entry in *existing*."""
    return any(
        name == entry or name in entry or entry.endswith(f"::{name}")
        for entry in existing
    )


def _extract_traceback_locations(
    text: str, near_pos: int, window: int = 2000
) -> list[str]:
    """Extract ``file:line`` locations near *near_pos* (looking backwards).

    Handles both the long (``File "...", line N``) and short
    (``path.py:N: in func``) traceback formats produced by pytest.
    """
    search_start = max(0, near_pos - window)
    region = text[search_start:near_pos]

    locations: list[str] = []
    for match in _FILE_LONG_RE.finditer(region):
        locations.append(f"{match.group(1)}:{match.group(2)}")
    for match in _FILE_SHORT_RE.finditer(region):
        locations.append(f"{match.group(2)}:{match.group(3)}")

    # De-duplicate while preserving order; keep the last few before the error.
    deduped: list[str] = []
    seen: set[str] = set()
    for loc in locations:
        if loc not in seen:
            seen.add(loc)
            deduped.append(loc)
    return deduped[-5:]
