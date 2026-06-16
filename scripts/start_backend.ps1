$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
if (!(Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python -m uvicorn app.main:app --reload --port 8000