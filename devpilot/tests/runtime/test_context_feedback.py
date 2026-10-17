"""The latest real outcome must drive model feedback."""
from devpilot.domain.state import DevPilotState, Observation
from devpilot.runtime.base import RuntimeConfig
from devpilot.runtime.custom.context import ContextBuilder
from devpilot.tools.registry import ToolRegistry
from tests.runtime.test_runner import _make_task


def test_successful_creation_is_not_reported_as_failure():
    builder = ContextBuilder(RuntimeConfig(), ToolRegistry())
    observation = Observation(step_id=1, source="tool", name="code.create_file",
        success=True, summary="OK", data={"path": "new.py", "modified_files": ["new.py"]})
    assert builder._format_observation_data(observation) == "[created: new.py]"


def test_latest_passing_test_supersedes_previous_failure():
    builder = ContextBuilder(RuntimeConfig(), ToolRegistry())
    state = DevPilotState(run_id="feedback", task=_make_task(), phase="verifying",
        observations=[
            Observation(step_id=1, source="tool", name="test.run", success=False,
                summary="fail", data={"test_failure": {"summary": "old failure"}}),
            Observation(step_id=2, source="tool", name="test.run", success=True,
                summary="pass", data={"passed": 1, "failed": 0})])
    assert "CURRENT TEST FAILURE" not in builder._build_state_content(state)
