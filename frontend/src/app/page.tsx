"use client";

import { useEffect, useState } from "react";
import { Controls } from "../components/Controls";
import { EngineerFeed } from "../components/EngineerFeed";
import { InputBars } from "../components/InputBars";
import { MetricCard } from "../components/MetricCard";
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

async function getHealth(): Promise<Partial<ControlState>> {
  const res = await fetch(`${API}/api/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
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

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-block no-logo">
          <div>
            <h1>Live Race Engineer</h1>
            <p>F1 UDP telemetry console</p>
          </div>
        </div>

        <section className="sidebar-section">
          <div className="side-label">Connection</div>

          <div className="connection-row">
            <span className={`dot ${snapshot.connected ? "green" : "amber"}`} />
            <div>
              <strong>UDP</strong>
              <p>{snapshot.connected ? "receiving" : "waiting"}</p>
            </div>
          </div>

          <div className="connection-row">
            <span className={`dot ${wsStatus === "connected" ? "green" : "red"}`} />
            <div>
              <strong>WebSocket</strong>
              <p>{wsLabel(wsStatus)}</p>
            </div>
          </div>

          <div className="connection-row">
            <span className={controls.voice_enabled ? "dot green" : "dot neutral"} />
            <div>
              <strong>Voice</strong>
              <p>{controls.voice_enabled ? "enabled" : "disabled"}</p>
            </div>
          </div>

          <div className="connection-row">
            <span className={controls.coaching_enabled ? "dot green" : "dot neutral"} />
            <div>
              <strong>Coach</strong>
              <p>{controls.coaching_enabled ? "enabled" : "disabled"}</p>
            </div>
          </div>
        </section>

        <section className="sidebar-section">
          <div className="side-label">Session</div>
          <div className="side-stat">
            <span>Packets</span>
            <strong>{snapshot.packet_count}</strong>
          </div>
          <div className="side-stat">
            <span>Frame</span>
            <strong>{snapshot.frame}</strong>
          </div>
          <div className="side-stat">
            <span>Format</span>
            <strong>{snapshot.packet_format ? `F1 ${snapshot.packet_format}` : "--"}</strong>
          </div>
          <div className="side-stat">
            <span>Track ID</span>
            <strong>{snapshot.track_id ?? "--"}</strong>
          </div>
        </section>

        <Controls
          voiceEnabled={controls.voice_enabled}
          coachingEnabled={controls.coaching_enabled}
          udpConnected={snapshot.connected}
          onStateChange={(next) => setControls((current) => ({ ...current, ...next }))}
          onReset={() => setSnapshot(emptySnapshot)}
        />

        {controls.last_voice_error ? <div className="side-error">Voice: {controls.last_voice_error}</div> : null}
        {controls.last_udp_error ? <div className="side-error">UDP: {controls.last_udp_error}</div> : null}
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Race control desk</p>
            <h2>Driver telemetry and live coaching</h2>
          </div>

          <div className="session-pill">
            <span className={snapshot.connected ? "live-dot on" : "live-dot"} />
            {snapshot.connected ? "Live telemetry" : "Waiting for UDP"}
          </div>
        </header>

        <section className="hero-strip">
          <div className="speed-tile">
            <span>Speed</span>
            <strong>{Math.round(snapshot.speed_kph)}</strong>
            <small>km/h</small>
          </div>

          <div className="gear-tile">
            <span>Gear</span>
            <strong>{gearLabel(snapshot.gear)}</strong>
            <small>{snapshot.rpm} rpm</small>
          </div>

          <MetricCard label="Lap" value={snapshot.lap_number || "--"} sub={`Sector ${snapshot.sector}`} />
          <MetricCard label="Current" value={msToLap(snapshot.current_lap_time_ms)} sub="lap time" />
          <MetricCard label="Best" value={msToLap(snapshot.best_lap_time_ms)} sub="personal best" />
          <MetricCard label="Fuel" value={fixed(snapshot.fuel_remaining_laps, 2)} sub="laps delta" />
          <MetricCard label="ERS" value={`${Math.round(snapshot.ers_percent)}%`} sub={`mode ${snapshot.ers_deploy_mode}`} />
        </section>

        <section className="lap-progress">
          <div className="lap-progress-head">
            <span>Lap distance</span>
            <strong>{Math.round(snapshot.lap_distance_m)} m</strong>
          </div>
          <div className="lap-progress-bar">
            <div style={{ width: `${trackProgress}%` }} />
          </div>
        </section>

        <section className="main-grid">
          <div className="left-stack">
            <TelemetryChart history={snapshot.history} />

            <div className="lower-grid">
              <InputBars throttle={snapshot.throttle} brake={snapshot.brake} steer={snapshot.steer} ers={snapshot.ers_percent} />
              <TyrePanel
                temps={snapshot.tyre_surface_temps_c}
                wear={snapshot.tyre_wear_pct}
                compound={snapshot.tyre_compound}
                age={snapshot.tyre_age_laps}
              />
            </div>

            <div className="panel car-status-panel">
              <div className="panel-heading">
                <h3>Car status</h3>
                <span className={snapshot.lap_invalid ? "state danger" : "state good"}>
                  {snapshot.lap_invalid ? "invalid lap" : "lap valid"}
                </span>
              </div>

              <div className="car-grid">
                <div><span>DRS</span><strong>{snapshot.drs ? "open" : snapshot.drs_allowed ? "available" : "closed"}</strong></div>
                <div><span>DRS range</span><strong>{snapshot.drs_activation_distance_m} m</strong></div>
                <div><span>Brake bias</span><strong>{snapshot.front_brake_bias}%</strong></div>
                <div><span>ABS</span><strong>{snapshot.abs_enabled ? "on" : "off"}</strong></div>
                <div><span>TC</span><strong>{snapshot.traction_control}</strong></div>
                <div><span>Warnings</span><strong>{snapshot.warnings}</strong></div>
                <div><span>Penalties</span><strong>{snapshot.penalties_s}s</strong></div>
                <div><span>Long G</span><strong>{fixed(snapshot.g_force_longitudinal, 2)}</strong></div>
                <div><span>Lat G</span><strong>{fixed(snapshot.g_force_lateral, 2)}</strong></div>
              </div>
            </div>
          </div>

          <aside className="right-stack">
            <EngineerFeed messages={snapshot.recent_messages} />
            <TrackMap snapshot={snapshot} />
          </aside>
        </section>
      </section>
    </main>
  );
}