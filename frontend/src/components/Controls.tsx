"use client";

import { useState } from "react";
import { ControlState } from "../types/telemetry";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type ControlsProps = {
  voiceEnabled: boolean;
  coachingEnabled: boolean;
  udpConnected: boolean;
  onStateChange: (next: Partial<ControlState>) => void;
  onReset?: () => void;
};

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function Controls({ voiceEnabled, coachingEnabled, udpConnected, onStateChange, onReset }: ControlsProps) {
  const [pending, setPending] = useState<string | null>(null);
  const [notice, setNotice] = useState("Ready");

  async function run(label: string, action: () => Promise<void>) {
    setPending(label);
    setNotice("Sending command...");
    try {
      await action();
      setNotice(`${label} confirmed`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Command failed");
    } finally {
      setPending(null);
    }
  }

  function statusText(value: boolean): string {
    return value ? "ON" : "OFF";
  }

  return (
    <div className="controls-panel">
      <div className="controls-head">
        <h3 className="controls-title">Controls</h3>
        <div className="mini-status-row">
          <span className={udpConnected ? "mini-status on" : "mini-status off"}>UDP {udpConnected ? "LIVE" : "WAIT"}</span>
          <span className={voiceEnabled ? "mini-status on" : "mini-status off"}>VOICE {statusText(voiceEnabled)}</span>
          <span className={coachingEnabled ? "mini-status on" : "mini-status off"}>COACH {statusText(coachingEnabled)}</span>
        </div>
      </div>

      <div className="controls-grid">
        <button
          className={`control-btn toggle ${voiceEnabled ? "active" : "inactive"}`}
          disabled={pending !== null}
          onClick={() =>
            run("Voice", async () => {
              const next = !voiceEnabled;
              const data = await postJson<{ voice_enabled: boolean }>(`/api/voice?enabled=${next}`);
              onStateChange({ voice_enabled: data.voice_enabled });
            })
          }
        >
          <span className="btn-dot" />
          Voice {statusText(voiceEnabled)}
        </button>

        <button
          className={`control-btn toggle ${coachingEnabled ? "active" : "inactive"}`}
          disabled={pending !== null}
          onClick={() =>
            run("Coaching", async () => {
              const next = !coachingEnabled;
              const data = await postJson<{ coaching_enabled: boolean }>(`/api/coaching?enabled=${next}`);
              onStateChange({ coaching_enabled: data.coaching_enabled });
            })
          }
        >
          <span className="btn-dot" />
          Coaching {statusText(coachingEnabled)}
        </button>

        <button
          className="control-btn"
          disabled={pending !== null}
          onClick={() =>
            run("Radio check", async () => {
              const data = await postJson<{ ok: boolean; last_voice_error?: string | null }>("/api/voice/test");
              onStateChange({ last_voice_error: data.last_voice_error ?? null });
            })
          }
        >
          Radio check
        </button>

        <button
          className="control-btn danger"
          disabled={pending !== null}
          onClick={() =>
            run("Reset", async () => {
              await postJson<{ ok: boolean }>("/api/reset");
              onReset?.();
            })
          }
        >
          Reset session
        </button>
      </div>

      <div className="control-notice">
        <span className={pending ? "notice-dot busy" : "notice-dot"} />
        {notice}
      </div>
    </div>
  );
}