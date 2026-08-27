"""Workspace configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkspaceConfig(BaseSettings):
    """Configuration for the workspace sandbox, loaded from environment."""

    workspace_root: str = "./workspaces"
    runs_root: str = "./runs"
    base_repo: str = "../shopflow-order-service"

    model_config = SettingsConfigDict(env_prefix="DEVPILOT_", env_file=".env")
