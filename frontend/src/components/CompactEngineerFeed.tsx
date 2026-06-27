"use client";

import { useMemo, useState } from "react";

import styles from "./CompactEngineerFeed.module.css";
import { EngineerMessage, RaceEvent } from "../types/telemetry";

type FeedItem = {
  id: string;
  timestamp: number;
  kind: "radio" | "event";
  severity: string;
  category: string;
  title: string;
  body: string;
};

function messageItems(messages: EngineerMessage[]): FeedItem[] {
  return messages.map((message) => ({
    id: `m-${message.id}`,
    timestamp: message.timestamp,
    kind: "radio",
    severity: message.severity,
    category: message.category,
    title: message.title,
    body: message.message,
  }));
}

function eventItems(events: RaceEvent[]): FeedItem[] {
  return events.map((event) => ({
    id: `e-${event.id}`,
    timestamp: event.timestamp,
    kind: "event",
    severity: event.severity,
    category: event.event_type,
    title: event.title,
    body: event.description,
  }));
}

export function CompactEngineerFeed({
  messages,
  events,
}: {
  messages: EngineerMessage[];
  events: RaceEvent[];
}) {
  const [tab, setTab] = useState<"radio" | "event">("radio");
  const feed = useMemo(() => {
    const rows = tab === "radio" ? messageItems(messages) : eventItems(events);
    return rows.sort((a, b) => b.timestamp - a.timestamp).slice(0, 80);
  }, [messages, events, tab]);

  return (
    <section className={styles.panel}>
      <header>
        <div>
          <span>Live calls</span>
          <strong>Race engineer</strong>
        </div>
        <nav>
          <button className={tab === "radio" ? styles.active : ""} onClick={() => setTab("radio")}>
            RADIO <b>{messages.length}</b>
          </button>
          <button className={tab === "event" ? styles.active : ""} onClick={() => setTab("event")}>
            EVENTS <b>{events.length}</b>
          </button>
        </nav>
      </header>

      <div className={styles.feed}>
        {feed.length === 0 ? (
          <div className={styles.empty}>
            <i />
            <span>WAITING FOR TELEMETRY</span>
          </div>
        ) : feed.map((item) => (
          <article className={`${styles.item} ${styles[item.severity] || ""}`} key={item.id}>
            <div>
              <strong>{item.title}</strong>
              <span>{item.category}</span>
            </div>
            <p>{item.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}