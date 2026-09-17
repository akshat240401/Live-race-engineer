$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Python telemetry engine on :8000..."
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$Root\scripts\start_backend.ps1"

Start-Sleep -Seconds 2
Write-Host "Starting TypeScript/Node.js backend on :8080..."
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$Root\scripts\start_node_backend.ps1"

Start-Sleep -Seconds 2
Write-Host "Starting Next.js frontend on :3000..."
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$Root\scripts\start_frontend.ps1"
