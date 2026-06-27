# Battle Command Dashboard v3

This update addresses the final dashboard issues found during 100% and 125% zoom testing.

## Changes

- removes the oversized lower diagnostics row from Battle Command;
- keeps trend values inside the ahead/behind rival cards;
- puts the configured DRS window directly in the forecast legend;
- uses a height-responsive Battle Command layout so the panel fits at increased browser zoom;
- shows `ANALYZING` instead of authoritative `CLEAR AIR` while the model's statistical confidence intervals overlap;
- resolves a state only when the dominant-state Wilson interval is separated from the runner-up interval;
- corrects ahead/behind trend wording and colour semantics;
- detects stale telemetry from backend packet age plus adaptive WebSocket cadence;
- displays a clear `TELEMETRY STALE` banner and dims frozen live values;
- preserves the plain black dashboard background and solid dark panels.

## Files updated

### Backend

- `backend/app/intelligence/__init__.py`
- `backend/app/intelligence/models.py`
- `backend/app/intelligence/engine.py`
- `backend/tests/test_intelligence_engine.py`
- validates/patches `backend/app/api/routes.py` only when the intelligence endpoint is missing
- appends the optional confidence setting to `backend/.env.example`

### Frontend

- `frontend/src/app/page.tsx`
- `frontend/src/app/RaceDashboard.module.css`
- `frontend/src/components/BattleCommandCenter.tsx`
- `frontend/src/components/BattleCommandCenter.module.css`
- `frontend/src/components/MiniTelemetryPlots.tsx`
- `frontend/src/components/MiniTelemetryPlots.module.css`
- `frontend/src/components/CompactEngineerFeed.tsx`
- `frontend/src/components/CompactEngineerFeed.module.css`
- `frontend/src/components/CompactTyreStatus.tsx`
- `frontend/src/components/CompactTyreStatus.module.css`
- `frontend/src/types/intelligence.ts`
- appends an optional stale-time override to `frontend/.env.local.example`

## Install

From the project root:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer

py -3.12 `
  "$env:USERPROFILE\Downloads\install_battle_dashboard_v3.py" `
  --project-root (Get-Location).Path
```

Backups are created under:

```text
%LOCALAPPDATA%\LiveRaceEngineer\upgrade-backups\battle-dashboard-v3-<timestamp>
```

## Backend validation

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\backend
.\.venv2\Scripts\Activate.ps1

python -m py_compile `
  app\intelligence\models.py `
  app\intelligence\engine.py `
  app\api\routes.py

python -m unittest tests.test_intelligence_engine -v
python -m unittest discover -s tests -v
```

## Frontend validation

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
& "C:\Program Files\nodejs\npx.cmd" tsc --noEmit
```

No TypeScript output means the check passed.

## Start

Backend:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\backend
.\.venv2\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue
& "C:\Program Files\nodejs\npm.cmd" run dev
```

Replay:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer
py -3.12 scripts\replay_udp_recording.py `
  ".\recordings\udp\f1_session_20260621_215525.lreudp" `
  --port 20778 `
  --speed 2
```

## Optional settings

Backend `.env`:

```env
INTELLIGENCE_STATE_CONFIDENCE_Z=1.96
```

The default is a 95% statistical separation test. Increasing it makes the dashboard more conservative before showing a resolved state.

Frontend `.env.local`:

```env
NEXT_PUBLIC_TELEMETRY_STALE_MS=1500
```

Leave it unset to use adaptive stale detection based on observed WebSocket cadence.