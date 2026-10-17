"""A later bad hunk must not silently commit an earlier valid hunk."""

from devpilot.tools.code.apply_patch import ApplyPatch, ApplyPatchInput
from devpilot.tools.context import ToolContext


async def test_mixed_valid_invalid_patch_leaves_files_unchanged(git_repo):
    original = (git_repo / "app.py").read_bytes()
    patch = (
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n-x = 1\n+x = 100\n y = 2\n"
        "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,2 +1,2 @@\n-does not exist\n"
        "+unexpected change\n neither does this\n"
    )
    result = await ApplyPatch().execute(
        ApplyPatchInput(patch=patch), ToolContext(workspace_root=str(git_repo), run_id="atomic")
    )
    assert not result.success
    assert (git_repo / "app.py").read_bytes() == original
    assert result.data["modified_files"] == []


async def test_crlf_file_accepts_lf_patch_without_normalizing_other_lines(git_repo):
    path = git_repo / "windows.py"
    path.write_bytes(b"value = 0\r\nuntouched = 1\r\n")
    patch = "--- a/windows.py\n+++ b/windows.py\n@@ -1 +1 @@\n-value = 0\n+value = 2\n"
    result = await ApplyPatch().execute(
        ApplyPatchInput(patch=patch), ToolContext(workspace_root=str(git_repo), run_id="crlf")
    )
    assert result.success, result.error
    assert b"value = 2" in path.read_bytes()
    assert b"untouched = 1\r\n" in path.read_bytes()
