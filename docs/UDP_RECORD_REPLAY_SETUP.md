# Live Race Engineer — Phase 1: Raw UDP Recording and Replay

This phase creates a reproducible copy of the exact F1 25 UDP datagrams and their arrival timing.
It does not change strategy logic or the dashboard yet.

## Why the proxy uses two ports

F1 25 sends telemetry to port `20777`.
The recorder listens on `20777`, stores every raw datagram, and forwards it unchanged to the backend on `20778`.

During recording/replay:

- F1 25 / recorder input: `20777`
- Backend input: `20778`

Only one process can bind to a UDP port, so the backend must temporarily use `20778` while the proxy owns `20777`.

## Files installed

- `scripts/record_udp_proxy.py`
- `scripts/replay_udp_recording.py`
- `scripts/analyze_udp_recording.py`

Recordings are written by default to:

`recordings/udp/f1_session_YYYYMMDD_HHMMSS.lreudp`

The raw recording contains the original bytes. Do not edit it.

## 1. Configure the backend port

Edit `backend/.env`:

```env
UDP_PORT=20778
```

Leave F1 25 configured as:

```text
UDP IP: 127.0.0.1
UDP Port: 20777
UDP Format: 2025
UDP Send Rate: 20 Hz or 30 Hz
```

Restart the backend after changing the port.

## 2. Start the backend

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer\backend
.\.venv2\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

The backend now listens for game telemetry on UDP `20778`.

## 3. Start the recorder/proxy

Open another PowerShell terminal:

```powershell
cd C:\Users\aksha\Desktop\FILES\MY-WORK\ai-race-engineer\ai-race-engineer
py -3.12 scripts\record_udp_proxy.py
```

Expected startup:

```text
Listening : 0.0.0.0:20777
Forwarding: 127.0.0.1:20778
Recording : ...\recordings\udp\f1_session_....lreudp
```

Do not run `simulate_udp.py` or `simulate_race_scenarios.py` at the same time as the real game.

## 4. Record a useful F1 25 session

A strong reference recording should include:

1. Grid/race start
2. Sector 1 → 2 → 3 transitions
3. Cars ahead and behind
4. One complete normal lap
5. Pit entry
6. Stop from soft to medium
7. Pit exit and a new-stint lap
8. At least one attack or defence battle
9. Final two laps and race finish

A 10–20 minute race is enough for the first dataset.

When finished, press `Ctrl+C` in the recorder terminal. It creates:

- `.lreudp` raw recording
- `.summary.json` recording summary

## 5. Analyze packet timing

```powershell
py -3.12 scripts\analyze_udp_recording.py `
  recordings\udp\f1_session_YYYYMMDD_HHMMSS.lreudp
```

This reports packet rates, inter-arrival timing, duplicate frames, backwards frames, and estimated missing frames.

## 6. Replay without opening F1 25

Keep the backend on UDP `20778`. Stop the recorder and close/disable game telemetry.

```powershell
py -3.12 scripts\replay_udp_recording.py `
  recordings\udp\f1_session_YYYYMMDD_HHMMSS.lreudp `
  --port 20778 `
  --speed 1
```

Replay twice as fast:

```powershell
py -3.12 scripts\replay_udp_recording.py <file> --port 20778 --speed 2
```

Replay as fast as possible for parser tests:

```powershell
py -3.12 scripts\replay_udp_recording.py <file> --port 20778 --speed 0
```

Replay a selected segment:

```powershell
py -3.12 scripts\replay_udp_recording.py <file> `
  --port 20778 `
  --start-seconds 240 `
  --duration-seconds 90
```

## 7. Return to the normal direct-game setup

Stop the proxy. Change `backend/.env` back to:

```env
UDP_PORT=20777
```

Restart the backend. F1 25 can then send directly to the backend again.

## Safety notes

- Keep raw recordings private if participant names or online session details are sensitive.
- The proxy forwards packets unchanged; it does not alter game input or control the car.
- The `.env` file must not be committed.
