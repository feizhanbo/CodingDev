"""CLI and evaluation depend on the public runtime protocol only."""

from types import SimpleNamespace

from typer.testing import CliRunner

from devpilot import cli
from devpilot.domain.result import AgentRunResult
from devpilot.runtime.contracts import RunOutcome


def test_default_and_explicit_fallback_build_expected_engines(monkeypatch):
    from devpilot.application.bootstrap import initialize_components
    from devpilot.llm.fake import FakeLLMClient
    from devpilot.llm.langchain import LangChainLLMClient
    from devpilot.llm.openai import OpenAIClient
    from devpilot.settings import Settings

    monkeypatch.delenv("DEVPILOT_RUNTIME", raising=False)
    monkeypatch.delenv("DEVPILOT_LLM_BACKEND", raising=False)
    settings = Settings(_env_file=None, api_key="synthetic-no-request")
    runner = initialize_components(settings=settings)
    assert runner.runtime_kind == "langgraph"
    assert isinstance(runner.agent.llm_client, LangChainLLMClient)
    fallback = settings.model_copy(update={"runtime": "custom", "llm_backend": "openai"})
    runner = initialize_components(settings=fallback)
    assert runner.runtime_kind == "custom"
    assert isinstance(runner.agent.llm_client, OpenAIClient)
    runner = initialize_components(settings=settings, fake=True)
    assert runner.runtime_kind == "langgraph"
    assert isinstance(runner.agent.llm_client, FakeLLMClient)


def test_cli_run_and_resume_use_public_port(tmp_path, monkeypatch):
    calls = []
    result = AgentRunResult(
        run_id="run_12345678", task_id="TASK", status="completed",
        phase="completed", total_steps=0, modified_files=[], observations=[],
    )
    outcome = RunOutcome(result=result, workspace="unused", artifacts="unused")

    async def execute(request):
        calls.append(request.task.id)
        return outcome

    async def resume(run_id):
        calls.append(run_id)
        return outcome

    port = SimpleNamespace(execute=execute, resume=resume)
    monkeypatch.setattr(cli, "create_runtime", lambda **options: port)
    issue = tmp_path / "issue.yaml"
    issue.write_text(
        "id: TASK\ntitle: Example\ndescription: Example\nacceptance_criteria: []\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    for args in (["run", str(issue), "--fake"], ["resume", "run_12345678"]):
        response = runner.invoke(cli.app, args)
        assert response.exit_code == 0, response.exception
    assert calls == ["TASK", "run_12345678"]
