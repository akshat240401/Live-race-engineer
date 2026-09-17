$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot\..\backend"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

if (!(Test-Path ".venv2\Scripts\python.exe")) {
    Write-Host "Creating backend virtual environment..."
    py -3.12 -m venv .venv2
}

& ".\.venv2\Scripts\Activate.ps1"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

python -m uvicorn app.main:app --reload --port 8000
