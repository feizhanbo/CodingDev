# DevPilot development helper script
# Usage: .\dev.ps1 lint | test | lint:devpilot | lint:shopflow | test:devpilot | test:shopflow

param(
    [Parameter(Position = 0)]
    [ValidateSet("lint", "test", "lint:devpilot", "lint:shopflow", "test:devpilot", "test:shopflow")]
    [string]$Action = "lint"
)

$ErrorActionPreference = "Stop"

switch ($Action) {
    "lint" {
        & .\dev.ps1 "lint:devpilot"
        & .\dev.ps1 "lint:shopflow"
    }
    "test" {
        & .\dev.ps1 "test:devpilot"
        & .\dev.ps1 "test:shopflow"
    }
    "lint:devpilot" {
        Push-Location devpilot
        uv run ruff check .
        Pop-Location
    }
    "lint:shopflow" {
        Push-Location shopflow-order-service
        uv run ruff check .
        Pop-Location
    }
    "test:devpilot" {
        Push-Location devpilot
        uv run pytest
        Pop-Location
    }
    "test:shopflow" {
        Push-Location shopflow-order-service
        uv run pytest
        Pop-Location
    }
}
