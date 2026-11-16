"""Only for orchestration unit tests; integration tests use TaskVerifier."""
from devpilot.verification.verifier import VerificationResult

class PassingVerifier:
    deadline = None

    def bind_snapshot(self, *args):
        pass

    async def verify(self, *args):
        return VerificationResult(success=True, checks=[])
