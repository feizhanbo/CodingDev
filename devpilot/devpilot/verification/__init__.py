"""Verification API, loaded lazily to keep policy tools runtime-independent."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devpilot.verification.verifier import TaskVerifier, VerificationResult

__all__ = ["TaskVerifier", "VerificationResult"]


def __getattr__(name: str):
    if name in __all__:
        from devpilot.verification import verifier

        return getattr(verifier, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
