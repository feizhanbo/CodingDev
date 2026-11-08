"""Single runtime selection boundary for CLI and evaluation."""

from devpilot.runtime.contracts import RuntimePort
from devpilot.settings import Settings


def create_runtime(*, settings: Settings | None = None, **options) -> RuntimePort:
    """Construct an adapter; per-execution dependencies belong to the adapter."""
    from devpilot.application.runtime import ApplicationRuntime

    settings = settings or Settings()
    return ApplicationRuntime(settings=settings, **options)
