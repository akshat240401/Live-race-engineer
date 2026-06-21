"use client";

import { useState } from "react";

import {
  EngineerMessage,
  RaceEvent,
} from "../types/telemetry";


function formatSessionTime(
  seconds: number,
): string {
  if (
    !Number.isFinite(seconds)
    || seconds < 0
  ) {
    return "--:--";
  }

  const minutes = Math.floor(
    seconds / 60
  );

  const remaining = Math.floor(
    seconds % 60
  );

  return (
    `${minutes}:`
    + String(remaining).padStart(
      2,
      "0",
    )
  );
}


export function EngineerFeed({
  messages,
  events = [],
}: {
  messages: EngineerMessage[];
  events?: RaceEvent[];
}) {
  const [tab, setTab] = useState<
    "radio" | "events"
  >("radio");

  return (
    <div className="panel panel-lg live-feed-panel">
      <div className="feed-header">
        <h2>
          {tab === "radio"
            ? "Race Engineer"
            : "Race Timeline"}
        </h2>

        <div className="feed-tabs">
          <button
            className={
              tab === "radio"
                ? "active"
                : ""
            }
            onClick={() => setTab("radio")}
          >
            Radio
          </button>

          <button
            className={
              tab === "events"
                ? "active"
                : ""
            }
            onClick={() => setTab("events")}
          >
            Events
            {events.length
              ? ` (${events.length})`
              : ""}
          </button>
        </div>
      </div>

      {tab === "radio" ? (
        <div className="messages radio-list">
          {messages.length === 0 && (
            <div className="message info radio-message">
              <div className="message-title radio-title">
                Waiting for telemetry
              </div>

              <div className="message-body radio-body">
                Start the UDP simulator or
                enable F1 UDP telemetry in-game.
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={
                `message radio-message `
                + message.severity
              }
            >
              <div className="message-title radio-title">
                {message.title}
              </div>

              <div className="message-body radio-body">
                {message.message}
              </div>

              <div className="message-meta radio-category">
                {message.category}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="messages radio-list timeline-list">
          {events.length === 0 && (
            <div className="message info radio-message">
              <div className="message-title radio-title">
                No race events yet
              </div>

              <div className="message-body radio-body">
                Position changes, incidents,
                penalties, laps, and session
                events will appear here.
              </div>
            </div>
          )}

          {events.map((event) => (
            <div
              key={event.id}
              className={
                `message radio-message `
                + event.severity
              }
            >
              <div className="timeline-meta">
                <span>
                  {formatSessionTime(
                    event.session_time,
                  )}
                </span>

                <span>
                  Lap {event.lap_number || "--"}
                </span>
              </div>

              <div className="message-title radio-title">
                {event.title}
              </div>

              <div className="message-body radio-body">
                {event.description}
              </div>

              <div className="message-meta radio-category">
                {event.event_type.replaceAll(
                  "_",
                  " ",
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}