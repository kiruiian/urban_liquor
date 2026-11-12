$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Project virtual environment not found. Create .venv and install requirements.txt first."
}
if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    throw "Missing .env. Copy .env.example to .env and configure the local database and secret key."
}

$frontend = Join-Path $PSScriptRoot "frontend"
$builtIndex = Join-Path $frontend "dist\index.html"
if (-not (Test-Path $builtIndex)) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        throw "Node.js and npm are required to build the frontend."
    }

    Push-Location $frontend
    try {
        if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
            & npm ci
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend dependency installation failed."
            }
        }

        $previousApiUrl = $env:VITE_API_URL
        $env:VITE_API_URL = "/api/v1"
        try {
            & npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed."
            }
        }
        finally {
            if ($null -eq $previousApiUrl) {
                Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
            }
            else {
                $env:VITE_API_URL = $previousApiUrl
            }
        }
    }
    finally {
        Pop-Location
    }
}

& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed; the app was not started."
}

Write-Host "Urban Liquor POS is available at http://127.0.0.1:8000"
Write-Host "Keep this window open while using the POS. Press Ctrl+C to stop it."
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
