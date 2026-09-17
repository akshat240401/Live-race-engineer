$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\node-backend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing Node backend dependencies..."
    npm install
}

npm run dev
