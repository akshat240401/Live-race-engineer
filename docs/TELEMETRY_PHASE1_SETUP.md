# Telemetry Correctness Phase 1

This upgrade adds transport-level correctness and observability without changing race strategy.

## What it implements

- immediate receive timestamps on every UDP datagram;
- packet parse, queue, state-update and end-to-end processing latency;
- session UID isolation;
- uint32-safe per-packet-type frame ordering;
- duplicate and out-of-order rejection;
- rejection of delayed packets from a retired session;
- automatic live-state reset when a genuinely new session UID appears;
- adaptive per-packet-group cadence estimates;
- per-field freshness metadata;
- live, warming-up, degraded and stale transport states;
- a `/api/telemetry/diagnostics` endpoint;
- focused unit and integration tests;
- a console diagnostics watcher.

## Files added

- `backend/app/telemetry/transport.py`
- `backend/tests/test_telemetry_transport.py`
- `backend/tests/test_telemetry_state_ordering.py`
- `scripts/test_telemetry_phase1.py`
- `docs/TELEMETRY_PHASE1_SETUP.md`

## Files replaced or patched

- replaced: `backend/app/udp/listener.py`
- patched: `backend/app/telemetry/models.py`
- patched: `backend/app/telemetry/state.py`
- patched: `backend/app/core/runtime.py`
- patched: `backend/app/api/routes.py`
- patched: `backend/.env.example`
- patched: `frontend/src/types/telemetry.ts`

The installer preserves each patched file's existing LF or CRLF newline style.

## Install

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer

py -3.12 `
  "$env:USERPROFILE\Downloads\install_telemetry_phase1.py" `
  --project-root (Get-Location).Path
```

Backups are written to:

```text
%LOCALAPPDATA%\LiveRaceEngineer\upgrade-backups\telemetry-phase1-<timestamp>
```

## Validate

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\backend
.\.venv2\Scripts\Activate.ps1

python -m py_compile `
  app\telemetry\transport.py `
  app\telemetry\models.py `
  app\telemetry\state.py `
  app\udp\listener.py `
  app\core\runtime.py `
  app\api\routes.py

python -m unittest tests.test_telemetry_transport -v
python -m unittest tests.test_telemetry_state_ordering -v
python -m unittest discover -s tests -v
```

Frontend type check:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\frontend
$env:Path = "C:\Program Files\nodejs;$env:Path"
& "C:\Program Files\nodejs\npx.cmd" tsc --noEmit
```

## Live/replay diagnostics

Start the backend, frontend and replay as usual. In another terminal:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer

py -3.12 scripts\test_telemetry_phase1.py `
  --interval 1 `
  --count 60
```

Detailed JSON:

```powershell
Invoke-RestMethod `
  "http://localhost:8000/api/telemetry/diagnostics" |
  ConvertTo-Json -Depth 30
```

## Expected behavior

During replay:

- `status` reaches `live`;
- accepted count rises continuously;
- duplicates and out-of-order counts normally remain zero;
- end-to-end latency stays low;
- `car_telemetry` and `lap_data` remain fresh.

After replay stops:

- `status` changes to `stale`;
- `last_packet_age_s` rises;
- frozen telemetry remains visible but is explicitly classified as stale.

Do not commit until the focused tests, complete backend suite, TypeScript check and real recording replay all pass.
