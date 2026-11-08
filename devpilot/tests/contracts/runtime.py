"""Compare business facts, excluding incidental IDs, paths and elapsed times."""


def assert_smoke_contract(result, state, diff):
    assert result.status == "completed", result.error
    assert [o.name for o in result.observations] == [
        "repo.search_code", "repo.read_file", "code.apply_patch", "test.run",
        "code.apply_patch", "code.create_file", "test.run",
    ]
    assert result.total_steps == 7
    assert result.budget["llm_requests"] == 8
    assert state["retry_count"] == 1
    assert "+    return a + b" in diff
    assert "test_addition_edges.py" in diff
    assert set(result.modified_files) == {"calculator.py", "tests/test_addition_edges.py"}
