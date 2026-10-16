"""Benchmark evidence must come from executed assertions on pinned inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from devpilot.evals.benchmark import (
    apply_dataset_patch,
    load_manifest,
    parse_junit,
    prepare_task,
    resource_root,
    run_independent_suite,
    verify_resources,
)


def test_eight_versioned_issues_have_bound_resources():
    manifest = load_manifest()
    assert set(manifest["issues"]) == {f"DEV-{n:03}" for n in range(1, 9)}
    for issue in manifest["issues"]:
        verify_resources(issue)
        assert (resource_root() / "benchmark" / issue / "reference.patch").stat().st_size > 0
        assert f"issues/{issue}.yaml" in manifest["issues"][issue]["resources"]


def test_modified_resource_fails_closed(monkeypatch):
    manifest = load_manifest()
    manifest["issues"]["DEV-001"]["resources"]["issues/DEV-001.yaml"] = "wrong"
    with pytest.raises(ValueError, match="resource changed"):
        verify_resources("DEV-001", manifest)


def test_task_start_is_reproducible_and_excludes_reference(tmp_path):
    base = Path(__file__).resolve().parents[2] / "shopflow-order-service"
    first = tmp_path / "first"
    second = tmp_path / "second"
    a = prepare_task(base, first, "DEV-007")
    b = prepare_task(base, second, "DEV-007")
    assert a["starting_tree"] == b["starting_tree"]
    code = (first / "app/services/order_service.py").read_text(encoding="utf-8")
    assert 'raise ValueError(f"Cannot pay order' not in code
    assert not (first / "reference.patch").exists()
    assert not (first / "hidden_tests").exists()
    assert not (first / "evals").exists()
    apply_dataset_patch(first, "DEV-007", "reference")
    assert 'raise ValueError(f"Cannot pay order' in (
        first / "app/services/order_service.py"
    ).read_text(encoding="utf-8")
    assert (first / "tests/test_issue_regression.py").is_file()


def test_baseline_drift_is_rejected_before_copy(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "app.py").write_text("changed", encoding="utf-8")
    import devpilot.evals.benchmark as benchmark

    manifest = {
        "baseline_commit": "pinned",
        "baseline_files": {"app.py": "wrong"},
        "issues": {"DEV-X": {"resources": {}}},
    }
    monkeypatch.setattr(benchmark, "load_manifest", lambda: manifest)
    with pytest.raises(ValueError, match="Baseline differs"):
        prepare_task(baseline, tmp_path / "out", "DEV-X")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "body,code,status",
    [
        ("", 0, "ERROR"),
        ('<testcase classname="t" name="one"><skipped/></testcase>', 0, "ERROR"),
        (
            '<testcase classname="t" name="one"><error>missing fixture</error></testcase>',
            1,
            "ERROR",
        ),
        (
            '<testcase classname="t" name="one"><failure>'
            'AssertionError: assert 1 == 2</failure></testcase>',
            1,
            "FAIL",
        ),
        ('<testcase classname="t" name="one"/>', 0, "PASS"),
        ('<testcase classname="t" name="one"/>', 1, "ERROR"),
        ('<testcase classname="t" name="one"/>' * 2, 0, "ERROR"),
    ],
)
def test_structured_report_semantics(tmp_path, body, code, status):
    path = tmp_path / "report.xml"
    path.write_text(f"<testsuite>{body}</testsuite>", encoding="utf-8")
    result = parse_junit(path, code)
    assert result.status == status
    if status == "FAIL":
        assert result.assertion_failures == 1


def test_missing_and_malformed_report_is_error(tmp_path):
    path = tmp_path / "report.xml"
    assert parse_junit(path, 0).status == "ERROR"
    path.write_text("bad xml", encoding="utf-8")
    assert parse_junit(path, 0).status == "ERROR"


def test_independent_suite_ignores_candidate_conftest_and_parent_config(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "implementation.py").write_text("VALUE = 17\n", encoding="utf-8")
    (candidate / "conftest.py").write_text(
        "raise RuntimeError('candidate conftest loaded')\n", encoding="utf-8"
    )
    (candidate / "pytest.ini").write_text("[pytest]\naddopts = --ignore=tests\n", encoding="utf-8")
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "test_impl.py").write_text(
        "from implementation import VALUE\ndef test_value(): assert VALUE == 17\n", encoding="utf-8"
    )
    monkeypatch.setenv("PYTEST_ADDOPTS", "--nonexistent-option")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "wrong"))
    report = run_independent_suite(
        candidate, suite, tmp_path / "out", sys.executable, trusted_fixtures=False
    )
    assert report.status == "PASS", report
    assert report.passed == 1
    assert report.report_file and Path(report.report_file).is_file()
    assert not (candidate / "tests").exists()
    json.loads(report.model_dump_json())
