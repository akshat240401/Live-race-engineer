# Live Race Engineer

A real-time AI race engineer and telemetry dashboard for EA SPORTS F1 25 / F1 25 2026 Season Pack.

Live Race Engineer listens to F1 UDP telemetry, maintains a live race state, gives race-engineer-style coaching, speaks useful calls aloud, and streams the session to a race-mode web dashboard.

The goal of this project is simple: turn raw racing telemetry into useful decisions while driving.

---

## Overview

Most racing games expose a lot of telemetry, but raw telemetry alone does not tell the driver what to improve. This project bridges that gap by combining:

* Real-time UDP telemetry processing
* Python/FastAPI backend services
* WebSocket-based live state streaming
* Rule-based race-engineer logic
* Voice feedback with cooldowns
* A compact race-mode dashboard built with Next.js
* Live telemetry trace, track map, tyre data, driver inputs, and race radio
* Foundation for post-race analysis and LLM/RAG-based performance review

The live system is designed to be fast and deterministic. The race engineer does not simply repeat every telemetry event. It decides what is useful, when to say it, and when to stay quiet.

---

## Features

### Real-time telemetry backend

* Listens to EA SPORTS F1 UDP telemetry on port `20777`
* Parses core F1 25 / 2026 Season Pack packet types used by the dashboard
* Maintains live session state
* Tracks lap timing, speed, throttle, brake, steering, tyres, ERS, fuel, damage, and car status
* Streams live state to the frontend over WebSockets
* Includes a built-in UDP simulator for testing without launching the game

### Race engineer coaching

* Detects useful driving patterns and session events
* Gives short race-engineer-style calls instead of long repeated sentences
* Uses cooldowns to avoid annoying repeated feedback
* Supports optional voice output using Python text-to-speech
* Displays all coaching messages in a live race radio feed

Examples of coaching signals:

* Brake/throttle overlap
* Poor throttle pickup
* Tyre overheating
* ERS usage issues
* Lap-time improvements
* New personal best
* Fuel and damage warnings
* Session/race-control style updates

### Race-mode dashboard

The frontend is designed to be usable while driving, not just as a data page.

Dashboard includes:

* Speed and gear
* Lap number, current lap, best lap
* Fuel, ERS, tyre wear
* Live telemetry trace
* Real telemetry-based track map
* Race engineer radio feed
* Driver input bars
* Tyre panel
* Car status panel
* Voice and coaching controls
* Radio check button
* Reset controls

The layout is optimized to keep important information visible without needing to scroll during a race.

### Live track map

Instead of using a fake circular lap map, the dashboard builds a track path from live world position telemetry.

As the car drives, the map draws the actual driven path and shows the current car position on that path.

### Telemetry trace

The telemetry trace shows driving signals over time and is built to support longer session history. It can be used to inspect throttle, brake, speed, and related driving behavior throughout the session.

### Voice engineer

The backend can speak race-engineer calls aloud while driving.

Voice can be toggled from the dashboard or API:

```text
POST /api/voice?enabled=true
POST /api/voice?enabled=false
```

A radio check endpoint is included so voice can be tested before starting a race.

---

## Tech Stack

### Backend

* Python
* FastAPI
* WebSockets
* UDP sockets
* Pydantic-style telemetry models
* Rule-based coaching engine
* Text-to-speech voice engineer

### Frontend

* Next.js
* React
* TypeScript
* CSS dashboard layout
* Canvas-based telemetry and track visualizations

### Tooling

* Git / GitHub
* PowerShell helper scripts
* Built-in UDP telemetry simulator

---

## Folder Structure

```text
Live-race-engineer/
  backend/
    app/
      api/
        routes.py
      coaching/
        radio.py
        rules.py
        voice.py
      core/
        config.py
        runtime.py
      f1/
        constants.py
        packets.py
      telemetry/
        models.py
        state.py
      udp/
        listener.py
      main.py
    requirements.txt
    .env.example

  frontend/
    src/
      app/
        globals.css
        layout.tsx
        page.tsx
      components/
        Controls.tsx
        EngineerFeed.tsx
        InputBars.tsx
        MetricCard.tsx
        TelemetryChart.tsx
        TrackMap.tsx
        TyrePanel.tsx
      lib/
        format.ts
      types/
        telemetry.ts
    package.json
    package-lock.json
    tsconfig.json
    .env.local.example

  scripts/
    simulate_udp.py
    start_backend.ps1
    start_frontend.ps1
    start_simulator.ps1

  docs/
    coaching_rules.md
    game_setup.md
```

---

## Current Status

This project is end-to-end runnable.

The included simulator allows the backend, frontend, dashboard, coaching system, and voice system to be tested without launching the game.

Real gameplay requires F1 UDP telemetry to be enabled in-game and may require allowing Python through Windows Firewall.

---

## Requirements

### Backend

* Python 3.12 recommended
* Windows, macOS, or Linux
* F1 25 / F1 25 2026 Season Pack for live gameplay
* UDP telemetry enabled in the game

### Frontend

* Node.js
* npm
* Modern browser

---

## Game Telemetry Setup

In F1 25 / F1 25 2026 Season Pack:

```text
Options -> Settings -> Telemetry Settings

UDP Telemetry: On
UDP Broadcast Mode: Off for same-PC use
UDP IP Address: 127.0.0.1
UDP Port: 20777
UDP Send Rate: 20Hz or 30Hz first
UDP Format: 2025
```

For console/network use:

```text
UDP Broadcast Mode: On
UDP IP Address: Your PC IPv4 address
UDP Port: 20777
```

To find your PC IPv4 address on Windows:

```powershell
ipconfig
```

Use the IPv4 address for your active Wi-Fi/Ethernet adapter.

---

## Quick Start on Windows

### 1. Clone the repository

```powershell
git clone https://github.com/akshat240401/Live-race-engineer.git
cd Live-race-engineer
```

### 2. Start the backend

Open Terminal 1:

```powershell
cd backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python -m uvicorn app.main:app --reload --port 8000
```

Backend should run at:

```text
http://localhost:8000
```

### 3. Start the frontend

Open Terminal 2:

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local -Force
npm run dev
```

Frontend should run at:

```text
http://localhost:3000
```

---

## Test Without the Game

Keep backend and frontend running.

Open Terminal 3 from the project root:

```powershell
py -3.12 scripts\simulate_udp.py
```

The dashboard should start updating with simulated telemetry.

You should see:

* Speed changing
* Gear changing
* Driver inputs moving
* Track map building
* Engineer messages appearing
* Voice calls if voice is enabled

Stop the simulator with:

```text
Ctrl + C
```

Do not run the simulator and the real game at the same time.

---

## API Endpoints

```text
GET  /
GET  /api/health
GET  /api/state
GET  /api/messages
POST /api/reset
POST /api/voice?enabled=true
POST /api/voice?enabled=false
POST /api/coaching?enabled=true
POST /api/coaching?enabled=false
POST /api/voice/test
WS   /ws/live
```

### Health check

```powershell
Invoke-RestMethod "http://localhost:8000/api/health" | ConvertTo-Json
```

Expected fields include:

```json
{
  "ok": true,
  "udp_running": true,
  "udp_port": 20777,
  "connected": true,
  "packet_count": 100,
  "voice_enabled": true,
  "coaching_enabled": true
}
```

---

## Voice Setup

The project uses local text-to-speech for voice calls.

To test voice directly:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

@"
import pyttsx3

engine = pyttsx3.init()
engine.setProperty("rate", 185)
engine.setProperty("volume", 0.9)
engine.say("Radio check. Live race engineer voice is working.")
engine.runAndWait()
"@ | python
```

To enable voice through the backend:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8000/api/voice?enabled=true"
```

To test voice through the app:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8000/api/voice/test"
```

---

## Why the Live Path Uses Rule-Based Logic

Live racing feedback needs to be fast, reliable, and predictable.

For that reason, the live race engineer uses deterministic telemetry rules and cooldowns instead of relying on a slow or unpredictable LLM during driving.

This makes live coaching suitable for real-time use:

* Low latency
* No network dependency
* No hallucinated live calls
* Easier to debug
* Easier to tune for specific driving behavior

LLMs are better suited for post-race analysis, where the system can review a full session and generate deeper recommendations.

---

## Planned LLM / RAG Post-Race Analysis

The next major layer is post-race analysis.

The idea is to save session data, telemetry history, coaching events, lap summaries, and race incidents, then use a retrieval-based workflow to find the most relevant moments from the race.

A future report could include:

* Where time was lost
* Repeated braking mistakes
* Throttle pickup issues
* Tyre degradation trends
* ERS usage patterns
* Overtakes and position changes
* Incident timeline
* Lap-by-lap comparison
* Improvement recommendations

Instead of generic advice, the system should reference actual session data.

Example:

```text
You repeatedly overlapped brake and throttle in slow corners during laps 4, 5, and 7.
Rear tyre temperature increased after those moments, and your exit speed dropped compared to your best lap.
Focus on releasing the brake earlier before applying throttle.
```

---

## Roadmap

### Live dashboard improvements

* Add race engineer alert banner
* Add race position panel
* Add gap to car ahead/behind
* Add sector delta display
* Add lap comparison view
* Improve track map with start/finish marker
* Save known track maps for instant loading

### Race engineer improvements

* Add quiet / balanced / coach / debug modes
* Improve braking analysis
* Improve throttle pickup analysis
* Add corner-specific feedback
* Add better cooldown tuning
* Add racecraft calls for overtakes and incidents

### Post-race analysis

* Save complete session history
* Generate lap-by-lap summaries
* Detect overtakes and position losses
* Detect possible crashes/contact
* Compare current race to previous sessions
* Add LLM/RAG-based post-race report generation

### Data and persistence

* Store sessions in local files
* Export telemetry as JSON/CSV
* Add session replay mode
* Add comparison between laps
* Add performance trend tracking over time

---

## Example Use Cases

### During a race

```text
Engineer: Brake and throttle overlap.
Engineer: Rear tyres are hot.
Engineer: Recharge ERS.
Engineer: Good lap. Personal best.
```

### After a race

```text
Summary:
Finished P6 after starting P10.
Best lap: 1:31.244.
Main time loss: braking release phase.
Main strength: traction on medium-speed exits.
Recommendation: reduce brake/throttle overlap and smooth throttle pickup.
```

---

## Development Workflow

Check changed files:

```powershell
git status --short --untracked-files=all
```

Commit backend work:

```powershell
git add backend/app
git commit -m "Improve telemetry backend"
```

Commit frontend work:

```powershell
git add frontend/src
git commit -m "Improve race dashboard"
```

Push:

```powershell
git push
```

---

## Troubleshooting

### Dashboard does not update

Check backend health:

```powershell
Invoke-RestMethod "http://localhost:8000/api/health" | ConvertTo-Json
```

Make sure:

```text
udp_running: true
connected: true
packet_count: increasing
```

If `packet_count` stays at `0`, the backend is not receiving UDP telemetry.

### Fake telemetry works, but game does not

Check:

* UDP telemetry is enabled in F1
* UDP IP is `127.0.0.1` for same-PC use
* UDP port is `20777`
* UDP format is set correctly
* Windows Firewall allows Python
* Simulator is not running at the same time as the game

### Voice test works, but no engineer voice

Check:

* Voice is enabled from dashboard or API
* Coaching is enabled
* Engineer messages are appearing
* Backend terminal shows voice logs
* Windows audio is not muted

### Hydration warning in browser

Some browser extensions inject attributes into the page and can trigger Next.js hydration warnings.

Try:

* Incognito/InPrivate mode
* Disabling grammar/rewriting extensions for `localhost:3000`
* Keeping `suppressHydrationWarning` in `layout.tsx`

---

## Project Motivation

This project started from a personal problem: I wanted more useful feedback while sim racing.

Raw telemetry is helpful, but only if it can be turned into decisions. The interesting engineering challenge was not just collecting data, but deciding what matters, when to act on it, and how to present it without distracting the driver.

That makes this project a mix of:

* Software engineering
* Real-time systems
* Automation
* Data processing
* Frontend UX
* AI-style decision logic
* Future LLM/RAG-based analysis

---

## Disclaimer

This project is an unofficial personal project and is not affiliated with, endorsed by, or connected to Formula 1, FIA, EA SPORTS, Codemasters, or any related organization.

EA SPORTS F1 telemetry formats belong to their respective owners.

---

## Repository

```text
https://github.com/akshat240401/Live-race-engineer
```

---

## Author

Akshat Paras Mehta
