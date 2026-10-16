# Run checks from any working directory; propagate native command failures.
param(
    [Parameter(Position = 0)]
    [ValidateSet("lint", "test", "lint:devpilot", "lint:shopflow", "test:devpilot", "test:shopflow")]
    [string]$Action = "lint"
)

$ErrorActionPreference = "Stop"
function Invoke-ProjectCheck {
    param([string]$Project, [string]$Check)
    Push-Location (Join-Path $PSScriptRoot $Project)
    try {
        if ($Check -eq "lint") {
            & uv run --frozen ruff check .
        } else {
            & uv run --frozen pytest
        }
        if ($LASTEXITCODE -ne 0) {
            throw "$Project $Check failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

try {
    switch ($Action) {
        "lint" { Invoke-ProjectCheck "devpilot" "lint"; Invoke-ProjectCheck "shopflow-order-service" "lint" }
        "test" { Invoke-ProjectCheck "devpilot" "test"; Invoke-ProjectCheck "shopflow-order-service" "test" }
        "lint:devpilot" { Invoke-ProjectCheck "devpilot" "lint" }
        "lint:shopflow" { Invoke-ProjectCheck "shopflow-order-service" "lint" }
        "test:devpilot" { Invoke-ProjectCheck "devpilot" "test" }
        "test:shopflow" { Invoke-ProjectCheck "shopflow-order-service" "test" }
    }
} catch {
    Write-Error -ErrorAction Continue $_
    exit 1
}
exit 0
