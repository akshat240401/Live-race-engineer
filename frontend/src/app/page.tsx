"use client";

import { useEffect, useState } from "react";
import { Controls } from "../components/Controls";
import { EngineerFeed } from "../components/EngineerFeed";
import { InputBars } from "../components/InputBars";
import { TelemetryChart } from "../components/TelemetryChart";
import { TrackMap } from "../components/TrackMap";
import { TyrePanel } from "../components/TyrePanel";
import { fixed, msToLap } from "../lib/format";
import { ControlState, TelemetrySnapshot } from "../types/telemetry";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/live";

const emptySnapshot: TelemetrySnapshot = {
  connected: false,
  packet_count: 0,
  last_packet_age_s: null,
  packet_format: null,
  game_year: null,
  session_time: 0,
  frame: 0,
  speed_kph: 0,
  throttle: 0,
  brake: 0,
  steer: 0,
  gear: 0,
  rpm: 0,
  drs: false,
  rev_lights_percent: 0,
  lap_number: 0,
  current_lap_time_ms: 0,
  last_lap_time_ms: 0,
  best_lap_time_ms: null,
  lap_distance_m: 0,
  track_length_m: null,
  track_id: null,
  position: 0,
  sector: 1,
  lap_invalid: false,
  warnings: 0,
  penalties_s: 0,
  fuel_remaining_laps: 0,
  fuel_in_tank_kg: 0,
  ers_store_j: 0,
  ers_percent: 0,
  ers_deploy_mode: 0,
  drs_allowed: false,
  drs_activation_distance_m: 0,
  tyre_age_laps: 0,
  tyre_compound: "UNKNOWN",
  front_brake_bias: 0,
  traction_control: 0,
  abs_enabled: false,
  brake_temps_c: [0, 0, 0, 0],
  tyre_surface_temps_c: [0, 0, 0, 0],
  tyre_inner_temps_c: [0, 0, 0, 0],
  tyre_pressures_psi: [0, 0, 0, 0],
  tyre_wear_pct: [0, 0, 0, 0],
  tyre_damage_pct: [0, 0, 0, 0],
  wing_damage_pct: { fl: 0, fr: 0, rear: 0 },
  world_position: [0, 0, 0],
  world_velocity: [0, 0, 0],
  g_force_lateral: 0,
  g_force_longitudinal: 0,
  completed_laps: [],
  recent_messages: [],
  history: [],
  track_points: [],
};

const emptyControls: ControlState = {
  voice_enabled: false,
  coaching_enabled: true,
  udp_running: false,
  last_voice_error: null,
  last_udp_error: null,
};

function gearLabel(gear: number): string {
  if (gear === 0) return "N";
  if (gear < 0) return "R";
  return String(gear);
}

function wsLabel(status: string): string {
  if (status === "connected") return "connected";
  if (status === "connecting") return "connecting";
  if (status === "error") return "error";
  return "offline";
}

function compactBool(value: boolean, on: string, off: string): string {
  return value ? on : off;
}

async function getHealth(): Promise<Partial<ControlState>> {
  const res = await fetch(`${API}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

function StatusChip({ label, value, active }: { label: string; value: string; active?: boolean }) {
  return (
    <div className={`status-chip ${active ? "active" : "idle"}`}>
      <span className="chip-dot" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SmallStat({ label, value, tone }: { label: string; value: string | number; tone?: "good" | "warn" | "danger" }) {
  return (
    <div className={`small-stat ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function Home() {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot>(emptySnapshot);
  const [controls, setControls] = useState<ControlState>(emptyControls);
  const [wsStatus, setWsStatus] = useState("connecting");

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (!active) return;

      setWsStatus("connecting");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => setWsStatus("connected");
      socket.onerror = () => setWsStatus("error");

      socket.onmessage = (event) => {
        try {
          setSnapshot(JSON.parse(event.data));
        } catch {
          // Keep the last valid telemetry snapshot.
        }
      };

      socket.onclose = () => {
        if (!active) return;
        setWsStatus("offline");
        retryTimer = setTimeout(connect, 1500);
      };
    }

    connect();

    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
      if (socket) socket.close();
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function refreshHealth() {
      try {
        const data = await getHealth();
        if (!active) return;
        setControls((current) => ({ ...current, ...data }));
      } catch {
        if (!active) return;
        setControls((current) => ({ ...current, udp_running: false }));
      }
    }

    refreshHealth();
    const id = setInterval(refreshHealth, 1500);

    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const trackProgress =
    snapshot.track_length_m && snapshot.track_length_m > 0
      ? Math.min(100, Math.max(0, (snapshot.lap_distance_m / snapshot.track_length_m) * 100))
      : 0;

  const brakeTone = snapshot.brake > 0.15 && snapshot.throttle > 0.15 ? "danger" : undefined;
  const tyreWearMax = Math.max(...snapshot.tyre_wear_pct.map((value) => value || 0));
  const tyreTone = tyreWearMax >= 65 ? "danger" : tyreWearMax >= 35 ? "warn" : undefined;

  return (
    <main className="race-shell">
      <header className="race-topbar">
        <div className="topbar-left">
          <div className="brand-line">
            <h1>Live Race Engineer</h1>
            <span>Race mode dashboard</span>
          </div>

          <div className="topbar-status">
            <StatusChip label="UDP" value={snapshot.connected ? "LIVE" : "WAIT"} active={snapshot.connected} />
            <StatusChip label="WS" value={wsLabel(wsStatus).toUpperCase()} active={wsStatus === "connected"} />
            <StatusChip label="VOICE" value={controls.voice_enabled ? "ON" : "OFF"} active={controls.voice_enabled} />
            <StatusChip label="COACH" value={controls.coaching_enabled ? "ON" : "OFF"} active={controls.coaching_enabled} />
          </div>
        </div>

        <div className="race-controls">
          <Controls
            voiceEnabled={controls.voice_enabled}
            coachingEnabled={controls.coaching_enabled}
            udpConnected={snapshot.connected}
            onStateChange={(next) => setControls((current) => ({ ...current, ...next }))}
            onReset={() => setSnapshot(emptySnapshot)}
          />
        </div>
      </header>

      <section className="race-content">
        <section className="primary-column">
          <section className="driver-strip">
            <div className="speed-box">
              <span>Speed</span>
              <strong>{Math.round(snapshot.speed_kph)}</strong>
              <small>km/h</small>
            </div>

            <div className="gear-box">
              <span>Gear</span>
              <strong>{gearLabel(snapshot.gear)}</strong>
              <small>{snapshot.rpm} rpm</small>
            </div>

            <SmallStat label="Lap" value={snapshot.lap_number || "--"} />
            <SmallStat label="Current" value={msToLap(snapshot.current_lap_time_ms)} />
            <SmallStat label="Best" value={msToLap(snapshot.best_lap_time_ms)} tone="good" />
            <SmallStat label="Fuel" value={fixed(snapshot.fuel_remaining_laps, 2)} tone={snapshot.fuel_remaining_laps < 0 ? "danger" : undefined} />
            <SmallStat label="ERS" value={`${Math.round(snapshot.ers_percent)}%`} tone={snapshot.ers_percent < 15 ? "warn" : undefined} />
            <SmallStat label="Tyres" value={`${Math.round(tyreWearMax)}%`} tone={tyreTone} />
          </section>

          <div className="lap-progress compact">
            <div className="lap-progress-bar">
              <div style={{ width: `${trackProgress}%` }} />
            </div>
            <span>{Math.round(snapshot.lap_distance_m)} m</span>
          </div>

          <section className="race-main-grid">
            <div className="race-map">
              <TrackMap snapshot={snapshot} />
            </div>

            <div className="race-chart">
              <TelemetryChart history={snapshot.history} />
            </div>
          </section>
        </section>

        <aside className="side-column">
          <div className="race-radio">
            <EngineerFeed messages={snapshot.recent_messages} />
          </div>

          <div className="race-inputs">
            <InputBars throttle={snapshot.throttle} brake={snapshot.brake} steer={snapshot.steer} ers={snapshot.ers_percent} />
          </div>

          <div className="race-tyres">
            <TyrePanel
              temps={snapshot.tyre_surface_temps_c}
              wear={snapshot.tyre_wear_pct}
              compound={snapshot.tyre_compound}
              age={snapshot.tyre_age_laps}
            />
          </div>

          <div className="panel compact-status-panel">
            <div className="panel-heading">
              <h3>Car status</h3>
              <span className={snapshot.lap_invalid ? "state danger" : "state good"}>
                {snapshot.lap_invalid ? "invalid" : "valid"}
              </span>
            </div>

            <div className="compact-status-grid">
              <SmallStat label="DRS" value={snapshot.drs ? "open" : compactBool(snapshot.drs_allowed, "ready", "closed")} />
              <SmallStat label="Bias" value={`${snapshot.front_brake_bias}%`} />
              <SmallStat label="ABS" value={snapshot.abs_enabled ? "on" : "off"} />
              <SmallStat label="TC" value={snapshot.traction_control} />
              <SmallStat label="Warn" value={snapshot.warnings} tone={snapshot.warnings > 0 ? "warn" : undefined} />
              <SmallStat label="Pen" value={`${snapshot.penalties_s}s`} tone={snapshot.penalties_s > 0 ? "danger" : undefined} />
              <SmallStat label="Long G" value={fixed(snapshot.g_force_longitudinal, 2)} />
              <SmallStat label="Lat G" value={fixed(snapshot.g_force_lateral, 2)} />
              <SmallStat label="Overlap" value={snapshot.brake > 0.15 && snapshot.throttle > 0.15 ? "yes" : "no"} tone={brakeTone} />
            </div>
          </div>

          {(controls.last_voice_error || controls.last_udp_error) && (
            <div className="side-error compact-error">
              {controls.last_voice_error ? <span>Voice: {controls.last_voice_error}</span> : null}
              {controls.last_udp_error ? <span>UDP: {controls.last_udp_error}</span> : null}
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}