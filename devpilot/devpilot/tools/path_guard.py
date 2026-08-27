"""Path guard enforcing workspace sandbox security rules.

Security rules (design doc 12.2):

* All paths must resolve to be within workspace root.
* Reject ``../`` traversal.
* Reject absolute paths outside workspace.
* Reject symlinks pointing outside workspace.
* Reject forbidden files: ``.env``, ``.git/config``, SSH keys.
* Reject path components matching forbidden patterns.
"""

from __future__ import annotations

from pathlib import Path


class PathGuard:
    """Validate that filesystem paths stay inside the workspace sandbox."""

    FORBIDDEN_FILES = {".env", ".git/config", ".ssh/id_rsa", ".ssh/id_ed25519"}
    FORBIDDEN_PATTERNS = [".env", "id_rsa", "id_ed25519"]

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def validate_path(self, path: str) -> Path:
        """Validate and return the resolved path.

        Raises :class:`PermissionError` with a descriptive message on any
        violation.
        """
        # 1. Join with workspace root if relative.
        raw = Path(path)
        candidate = raw if raw.is_absolute() else self.workspace_root / raw

        # 2. Resolve the path (follows symlinks, normalizes "..").
        resolved = candidate.resolve()

        # 3. The resolved path must live under workspace root.
        if not resolved.is_relative_to(self.workspace_root):
            raise PermissionError(
                f"Path '{path}' resolves outside workspace root"
            )

        # 4. Reject symlinks pointing outside the workspace.
        self._check_symlinks(candidate)

        # 5 & 6. Forbidden files / patterns checked against the workspace-
        # relative portion so the workspace root itself never triggers a
        # false positive.
        rel_str = resolved.relative_to(self.workspace_root).as_posix()
        self._check_forbidden(rel_str)

        return resolved

    def _check_symlinks(self, candidate: Path) -> None:
        """Walk path components and reject symlinks escaping the workspace."""
        try:
            rel = candidate.relative_to(self.workspace_root)
        except ValueError:
            # Not lexically under workspace; the resolved-containment check
            # above already guards this case.
            return

        accumulated = self.workspace_root
        for part in rel.parts:
            accumulated = accumulated / part
            if accumulated.is_symlink():
                target = accumulated.resolve()
                if not target.is_relative_to(self.workspace_root):
                    raise PermissionError(
                        f"Symlink '{accumulated}' points outside workspace root"
                    )

    def _check_forbidden(self, rel_str: str) -> None:
        """Reject forbidden files and patterns in the relative path."""
        for forbidden in self.FORBIDDEN_FILES:
            if rel_str == forbidden or rel_str.startswith(forbidden + "/"):
                raise PermissionError(
                    f"Access to forbidden file '{forbidden}' is denied"
                )
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in rel_str:
                raise PermissionError(
                    f"Access to forbidden path pattern '{pattern}' is denied"
                )
