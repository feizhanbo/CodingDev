param([switch]$Build)
$ErrorActionPreference = 'Stop'
if ($Build -or !(Test-Path "$PSScriptRoot/web/dist/index.html")) {
    Push-Location "$PSScriptRoot/web"
    try {
        & npm ci --cache ../runs/npm-cache
        if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
Push-Location "$PSScriptRoot/shopflow-order-service"
try {
    & uv sync --frozen --cache-dir ../runs/uv-cache
    if ($LASTEXITCODE -ne 0) { throw 'ShopFlow dependencies failed' }
} finally { Pop-Location }
Push-Location "$PSScriptRoot/devpilot"
try {
    & uv run --frozen --cache-dir ../runs/uv-cache python -m devpilot.web.server
    if ($LASTEXITCODE -ne 0) { throw 'Workbench exited with an error' }
} finally { Pop-Location }
