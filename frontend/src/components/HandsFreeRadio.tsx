"use client";

import {
  ChangeEvent,
  FormEvent,
  useEffect,
  useMemo,
  useState,
} from "react";

import styles from "./HandsFreeRadio.module.css";
import { StrategicEngineerCard } from "./StrategicEngineerCard";
import {
  RadioMode,
  RadioStatus,
  RadioTranscriptEntry,
} from "../types/telemetry";

const API =
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000";

const emptyStatus: RadioStatus = {
  enabled: false,
  running: false,
  state: "disabled",
  mode: "race",
  muted: false,
  conversation_open: false,
  awaiting_command: false,
  command_timeout_s: 8,
  command_time_remaining_s: 0,
  wake_phrases: ["engineer"],
  input_device: null,
  input_device_name: null,
  stt_model: "base.en",
  stt_ready: false,
  llm_enabled: false,
  barge_in_enabled: false,
  ack_mode: "beep",
  response_style: "concise",
  noise_floor_rms: 0,
  calibrating: false,
  calibration_remaining_s: 0,
  pending_auto_messages: 0,
  pending_confirmation: null,
  last_heard: null,
  last_normalized: null,
  last_response: null,
  last_error: null,
  last_activity_at: null,
  transcript_count: 0,
};

async function requestJSON<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      detail || `${response.status} ${response.statusText}`,
    );
  }

  return response.json() as Promise<T>;
}

function stateLabel(state: RadioStatus["state"]): string {
  return state.replaceAll("_", " ").toUpperCase();
}

function timeLabel(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function guidance(status: RadioStatus): string {
  if (status.last_error) {
    return status.last_error;
  }
  if (!status.enabled) {
    return "Hands-free listening is disabled.";
  }
  if (status.calibrating) {
    return `Stay quiet while the microphone calibrates — ${status.calibration_remaining_s.toFixed(1)}s remaining.`;
  }
  if (status.awaiting_command) {
    return `Listening now — ask your question within ${status.command_time_remaining_s.toFixed(1)} seconds.`;
  }
  if (status.state === "transcribing") {
    return "Transcribing your radio call...";
  }
  if (status.state === "thinking") {
    return "Engineer is checking live telemetry...";
  }
  if (status.state === "speaking") {
    return "Engineer speaking.";
  }
  if (status.conversation_open) {
    return "Follow-up window open — ask another question without repeating the wake phrase.";
  }
  return `Say “${status.wake_phrases[0] || "engineer"}”. Wait for the ${status.ack_mode} acknowledgement, then ask your question.`;
}

export function HandsFreeRadio() {
  const [status, setStatus] =
    useState<RadioStatus>(emptyStatus);
  const [transcript, setTranscript] =
    useState<RadioTranscriptEntry[]>([]);
  const [testText, setTestText] = useState(
    "Engineer, what is the gap ahead?",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(
    "Connecting to hands-free radio...",
  );

  useEffect(() => {
    let active = true;

    async function refresh() {
      try {
        const [nextStatus, transcriptPayload] =
          await Promise.all([
            requestJSON<RadioStatus>(
              `${API}/api/radio/status`,
            ),
            requestJSON<{
              items: RadioTranscriptEntry[];
            }>(`${API}/api/radio/transcript?limit=16`),
          ]);

        if (!active) {
          return;
        }

        setStatus(nextStatus);
        setTranscript(transcriptPayload.items);
        setMessage(guidance(nextStatus));
      } catch (error) {
        if (!active) {
          return;
        }
        setMessage(
          error instanceof Error
            ? error.message
            : "Radio status unavailable",
        );
      }
    }

    refresh();
    const interval = setInterval(refresh, 500);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const lastEntries = useMemo(
    () => transcript.slice(-8),
    [transcript],
  );

  async function toggleEnabled() {
    setBusy(true);
    try {
      const next = await requestJSON<RadioStatus>(
        `${API}/api/radio/enabled?enabled=${!status.enabled}`,
        { method: "POST" },
      );
      setStatus(next);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not change radio state",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeMode(mode: RadioMode) {
    setBusy(true);
    try {
      const next = await requestJSON<RadioStatus>(
        `${API}/api/radio/mode?mode=${mode}`,
        { method: "POST" },
      );
      setStatus(next);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not change radio mode",
      );
    } finally {
      setBusy(false);
    }
  }

  async function openConversation() {
    setBusy(true);
    try {
      const next = await requestJSON<RadioStatus>(
        `${API}/api/radio/listen?acknowledge=true`,
        { method: "POST" },
      );
      setStatus(next);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not open listening window",
      );
    } finally {
      setBusy(false);
    }
  }

  async function calibrateNoise() {
    setBusy(true);
    try {
      const result = await requestJSON<{
        status: RadioStatus;
      }>(`${API}/api/radio/calibrate?duration_s=5`, {
        method: "POST",
      });
      setStatus(result.status);
      setMessage(
        "Noise calibration started. Stay quiet for five seconds.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not calibrate microphone",
      );
    } finally {
      setBusy(false);
    }
  }

  async function toggleQuiet() {
    setBusy(true);
    try {
      const next = await requestJSON<RadioStatus>(
        `${API}/api/radio/quiet?quiet=${!status.muted}`,
        { method: "POST" },
      );
      setStatus(next);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not change quiet mode",
      );
    } finally {
      setBusy(false);
    }
  }

  async function repeatLast() {
    setBusy(true);
    try {
      await requestJSON(
        `${API}/api/radio/repeat?speak=true`,
        { method: "POST" },
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not repeat message",
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitTest(event: FormEvent) {
    event.preventDefault();
    if (!testText.trim()) {
      return;
    }

    setBusy(true);
    try {
      const result = await requestJSON<{
        response?: string;
      }>(`${API}/api/radio/test`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: testText.trim(),
          speak: true,
        }),
      });
      setMessage(
        result.response || "Test command sent.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Test command failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel}>
      <div className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>
            Two-way race radio
          </span>
          <h3>Hands-free engineer</h3>
        </div>

        <span
          className={`${styles.state} ${
            styles[status.state] || ""
          }`}
        >
          {stateLabel(status.state)}
        </span>
      </div>

      <div className={styles.listenBanner}>
        <span
          className={`${styles.listenDot} ${
            status.awaiting_command || status.state === "listening"
              ? styles.listenDotActive
              : ""
          }`}
        />
        <div>
          <strong>
            {status.awaiting_command
              ? "ASK NOW"
              : status.calibrating
                ? "CALIBRATING"
                : "WAKE WORD READY"}
          </strong>
          <span>{message}</span>
        </div>
      </div>

      <StrategicEngineerCard />

      <div className={styles.metaGrid}>
        <div>
          <span>Microphone</span>
          <strong>
            {status.input_device_name ||
              "Default input"}
          </strong>
        </div>
        <div>
          <span>Acknowledgement</span>
          <strong>{status.ack_mode}</strong>
        </div>
        <div>
          <span>Speech model</span>
          <strong>
            {status.stt_model}{" "}
            {status.stt_ready ? "ready" : "loading"}
          </strong>
        </div>
        <div>
          <span>Response style</span>
          <strong>{status.response_style}</strong>
        </div>
        <div>
          <span>Noise floor</span>
          <strong>{status.noise_floor_rms.toFixed(0)} RMS</strong>
        </div>
        <div>
          <span>Queued calls</span>
          <strong>{status.pending_auto_messages}</strong>
        </div>
      </div>

      <div className={styles.controls}>
        <button
          type="button"
          onClick={toggleEnabled}
          disabled={busy}
          className={status.enabled ? styles.activeButton : ""}
        >
          {status.enabled ? "Listening on" : "Enable listening"}
        </button>

        <button
          type="button"
          onClick={openConversation}
          disabled={busy || !status.enabled}
        >
          Beep + listen
        </button>

        <button
          type="button"
          onClick={calibrateNoise}
          disabled={busy || !status.enabled || status.calibrating}
        >
          {status.calibrating ? "Calibrating..." : "Calibrate noise"}
        </button>

        <button
          type="button"
          onClick={repeatLast}
          disabled={busy}
        >
          Repeat
        </button>

        <button
          type="button"
          onClick={toggleQuiet}
          disabled={busy}
          className={status.muted ? styles.warningButton : ""}
        >
          {status.muted ? "Resume updates" : "Quiet auto calls"}
        </button>
      </div>

      <div className={styles.modeRow}>
        {(["minimal", "race", "coaching"] as RadioMode[]).map(
          (mode) => (
            <button
              type="button"
              key={mode}
              onClick={() => changeMode(mode)}
              disabled={busy}
              className={
                status.mode === mode ? styles.selectedMode : ""
              }
            >
              {mode}
            </button>
          ),
        )}
      </div>

      {status.pending_confirmation ? (
        <p className={styles.confirmation}>
          Confirmation required: {status.pending_confirmation}. Say
          “confirm” or “cancel”.
        </p>
      ) : null}

      <div className={styles.transcript}>
        {lastEntries.length === 0 ? (
          <p className={styles.empty}>
            No radio conversation yet.
          </p>
        ) : (
          lastEntries.map((entry) => (
            <div
              key={entry.id}
              className={`${styles.entry} ${
                entry.speaker === "driver"
                  ? styles.driver
                  : entry.speaker === "engineer"
                    ? styles.engineer
                    : styles.system
              }`}
            >
              <div>
                <strong>{entry.speaker}</strong>
                <span>{timeLabel(entry.timestamp)}</span>
              </div>
              <p>{entry.text}</p>
            </div>
          ))
        )}
      </div>

      <form
        className={styles.testForm}
        onSubmit={submitTest}
      >
        <input
          value={testText}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            setTestText(event.target.value)
          }
          aria-label="Manual radio test command"
          placeholder="Test a radio question"
        />
        <button type="submit" disabled={busy}>
          Test
        </button>
      </form>
    </section>
  );
}
