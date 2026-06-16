$ErrorActionPreference = "Stop"
$env:Path = "C:\Program Files\nodejs;$env:Path"
Set-Location "$PSScriptRoot\..\frontend"
& "C:\Program Files\nodejs\npm.cmd" install
Copy-Item .env.local.example .env.local -Force
& "C:\Program Files\nodejs\npm.cmd" run dev