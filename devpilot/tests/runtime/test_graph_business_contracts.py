"""Apply the existing custom-runtime business assertions to the real graph.

The original modules continue to test custom; these subclasses change only their
runner construction boundary, preserving fixtures, decisions and assertions.
"""

import pytest

from devpilot.runtime.langgraph.runner import LangGraphAgentRunner
from tests import test_planning_flow as planning
from tests.runtime import test_repair_loop as repair
from tests.runtime import test_self_correction as correction


@pytest.fixture(autouse=True)
def graph_backend(monkeypatch):
    for module in (planning, repair, correction):
        monkeypatch.setattr(module, "CustomAgentRunner", LangGraphAgentRunner)


class TestGraphRepairFlow(repair.TestRepairFlowSucceeds):
    pass


class TestGraphPlanLoopTermination(repair.TestInfinitePlanUpdateTerminated):
    pass


class TestGraphDuplicateAction(repair.TestDuplicateActionRegression):
    pass


class TestGraphSelfCorrection(correction.TestRepairLoopComplete):
    pass


class TestGraphRetryLimit(correction.TestMaxRetriesExceeded):
    pass


class TestGraphVerifierRejection(correction.TestVerifierRejectsEmptyDiff):
    pass


class TestGraphRepairTrace(correction.TestTraceEventsRecorded):
    pass


class TestGraphWithoutVerifier(correction.TestBackwardCompatNoVerifier):
    pass


class TestGraphPlanCreation(planning.TestPlanCreation):
    pass


class TestGraphPlanContext(planning.TestPlanVisibleInContext):
    pass


class TestGraphPlanRepair(planning.TestPlanUpdateDuringRepair):
    pass


class TestGraphPlanTrace(planning.TestPlanTraceEvents):
    pass
