# Battle Command Center v1

This upgrade replaces the track map, combined telemetry chart, large hands-free card, and generic strategy card with:

- three minimal synchronized plots: Speed, Throttle, Brake;
- an adaptive Battle Command panel;
- gap forecasts for the car ahead and behind;
- learned attack / defence / contested / clear probabilities;
- rival pressure and model-quality visuals;
- a compact decision timeline;
- compact tyre status and car status;
- a compact Race Engineer feed.

## Important design note

A literally zero-hardcoded system is not technically possible. Software needs data-validation rules, model mechanics, UI labels, and game-rule constants. This implementation removes hardcoded race decisions, fixed battery percentages, canned attack thresholds, and canned strategy sentences.

The only race-domain constant used by the battle model is the DRS eligibility window, which is configurable and defaults to the F1 rule value of 1.0 second. Every battle probability, gap forecast, trend, confidence, target, and state is learned from the active session.

The live intelligence model uses:

- robust median-absolute-deviation outlier filtering;
- session-trained linear gap regression;
- model uncertainty and confidence intervals;
- probabilistic DRS-window forecasts;
- data-driven state inference for attack, defence, contested, and clear-air conditions;
- session-reset protection;
- dynamic rival tracking by driver identity.

It does not use an LLM to invent strategy numbers. An LLM can later verbalize the structured model output, but the numerical decision layer remains telemetry-grounded.

## Files installed

### Backend

- `backend/app/intelligence/__init__.py`
- `backend/app/intelligence/models.py`
- `backend/app/intelligence/engine.py`
- `backend/tests/test_intelligence_engine.py`
- patches `backend/app/api/routes.py`
- appends optional settings to `backend/.env.example`

### Frontend

- `frontend/src/app/page.tsx`
- `frontend/src/app/RaceDashboard.module.css`
- `frontend/src/components/MiniTelemetryPlots.tsx`
- `frontend/src/components/MiniTelemetryPlots.module.css`
- `frontend/src/components/BattleCommandCenter.tsx`
- `frontend/src/components/BattleCommandCenter.module.css`
- `frontend/src/components/CompactEngineerFeed.tsx`
- `frontend/src/components/CompactEngineerFeed.module.css`
- `frontend/src/components/CompactTyreStatus.tsx`
- `frontend/src/components/CompactTyreStatus.module.css`
- `frontend/src/types/intelligence.ts`

## Install

From the project root:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer

py -3.12 "$env:USERPROFILE\Downloads\install_battle_command_center_v1.py" `
  --project-root (Get-Location).Path
```

The installer creates backups under:

```text
%LOCALAPPDATA%\LiveRaceEngineer\upgrade-backups\battle-command-center-v1-<timestamp>
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
```

## Frontend validation

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\frontend

$env:Path = "C:\Program Files\nodejs;$env:Path"

& "C:\Program Files\nodejs\npx.cmd" tsc --noEmit
```

No output means the TypeScript check passed.

## Start the backend

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\backend

.\.venv2\Scripts\Activate.ps1

python -m uvicorn app.main:app --reload --port 8000
```

## Start the frontend

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\frontend

$env:Path = "C:\Program Files\nodejs;$env:Path"

Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue

& "C:\Program Files\nodejs\npm.cmd" run dev
```

## Test with the real recording

Keep F1 25 closed and do not run the UDP recorder or synthetic simulator.

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer

py -3.12 scripts\replay_udp_recording.py `
  ".\recordings\udp\f1_session_20260621_215525.lreudp" `
  --port 20778 `
  --speed 2
```

Open:

```text
http://localhost:3000
```

## Inspect the learned model directly

```powershell
Invoke-RestMethod `
  "http://localhost:8000/api/intelligence/live" |
  ConvertTo-Json -Depth 20
```

The response includes:

- model sample count;
- data quality;
- car-ahead and car-behind models;
- gap trend per lap;
- closing probability;
- predicted next-lap gap;
- DRS probability;
- attack / defend / contested / clear probabilities;
- three-lap forecast;
- decision timeline.

## Optional model settings

These settings are appended to `.env.example`. They are optional because the code has safe defaults.

```env
INTELLIGENCE_DRS_WINDOW_S=1.0
INTELLIGENCE_HISTORY_SECONDS=180
INTELLIGENCE_FORECAST_LAPS=3
INTELLIGENCE_TIMELINE_SIZE=12
```