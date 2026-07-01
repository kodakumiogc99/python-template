# run.ps1 — Windows launcher for create_project.py
#
# Does NOT require Python to be pre-installed.
# Installs uv (a Rust binary) if missing, then uses uv to run the script.
# uv will download Python automatically if needed.
#
# Usage:
#   .\run.ps1                              # interactive
#   .\run.ps1 my-tool                      # pre-fill name
#   .\run.ps1 my-api --type api --yes      # non-interactive
#   .\run.ps1 --help

$ErrorActionPreference = "Stop"

# ── Install uv if missing ─────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Installing..." -ForegroundColor Cyan

    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Write-Host "ERROR: Failed to download uv installer." -ForegroundColor Red
        Write-Host "  Check your internet connection or install manually:"
        Write-Host "  https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }

    # Refresh PATH in the current session
    $uvPaths = @(
        "$env:USERPROFILE\.local\bin",
        "$env:APPDATA\uv\bin",
        "$env:USERPROFILE\.cargo\bin"
    )
    foreach ($p in $uvPaths) {
        if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
            $env:PATH = "$p;$env:PATH"
        }
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: uv installed but not found in PATH." -ForegroundColor Red
        Write-Host "  Please restart your terminal and run this script again."
        exit 1
    }

    Write-Host "uv installed successfully." -ForegroundColor Green
    Write-Host ""
}

# ── Run the script via uv ─────────────────────────────────────
# uv will download Python automatically if not present (guided by PEP 723 header)
$scriptPath = Join-Path $PSScriptRoot "create_project.py"
uv run $scriptPath @args
