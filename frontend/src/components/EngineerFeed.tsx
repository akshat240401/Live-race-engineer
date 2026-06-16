import { EngineerMessage } from "../types/telemetry";

function severityText(severity: string): string {
  if (severity === "danger") return "critical";
  if (severity === "warning") return "warning";
  if (severity === "success") return "clear";
  return "engineer";
}

export function EngineerFeed({ messages }: { messages: EngineerMessage[] }) {
  const feed = messages.length
    ? messages
    : [
        {
          id: -1,
          timestamp: Date.now(),
          severity: "info",
          category: "system",
          title: "Waiting for telemetry",
          message: "Enable F1 UDP telemetry in-game, then start driving.",
          evidence: {},
        },
      ];

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Race engineer radio</h3>
        <span className="state good">feed</span>
      </div>

      <div className="radio-list">
        {feed.map((message) => (
          <div key={message.id} className={`radio-message ${message.severity}`}>
            <div className="radio-meta">{severityText(message.severity)}</div>
            <div className="radio-title">{message.title}</div>
            <div className="radio-body">{message.message}</div>
            <div className="radio-category">{message.category}</div>
          </div>
        ))}
      </div>
    </div>
  );
}