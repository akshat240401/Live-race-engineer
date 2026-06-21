"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  AIReport,
  PostRaceReport,
  RaceEvent,
  SessionListItem,
} from "../../types/telemetry";


const API =
  process.env.NEXT_PUBLIC_API_BASE
  || "http://localhost:8000";


function formatLap(
  seconds: number | null | undefined,
): string {
  if (
    seconds === null
    || seconds === undefined
    || !Number.isFinite(seconds)
    || seconds <= 0
  ) {
    return "--:--.---";
  }

  const minutes = Math.floor(
    seconds / 60
  );

  const remainder =
    seconds - minutes * 60;

  return (
    `${minutes}:`
    + remainder
      .toFixed(3)
      .padStart(6, "0")
  );
}


function formatDate(
  value: string | null,
): string {
  if (!value) return "--";

  const date = new Date(value);

  if (Number.isNaN(date.valueOf())) {
    return value;
  }

  return date.toLocaleString();
}


function EventCard({
  event,
}: {
  event: RaceEvent;
}) {
  return (
    <div
      className={
        `report-event ${event.severity}`
      }
    >
      <div className="report-event-meta">
        <span>
          Lap {event.lap_number || "--"}
        </span>

        <span>
          {event.event_type.replaceAll(
            "_",
            " ",
          )}
        </span>
      </div>

      <strong>{event.title}</strong>
      <p>{event.description}</p>
    </div>
  );
}


export default function ReportsPage() {
  const [sessions, setSessions] =
    useState<SessionListItem[]>([]);

  const [selected, setSelected] =
    useState("");

  const [report, setReport] =
    useState<PostRaceReport | null>(null);

  const [aiReport, setAIReport] =
    useState<AIReport | null>(null);

  const [question, setQuestion] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [message, setMessage] =
    useState("Loading sessions...");

  async function loadSessions() {
    const response = await fetch(
      `${API}/api/sessions`,
      {
        cache: "no-store",
      },
    );

    if (!response.ok) {
      throw new Error(
        "Could not load saved sessions",
      );
    }

    const data = await response.json() as {
      sessions: SessionListItem[];
    };

    setSessions(data.sessions);

    if (
      !selected
      && data.sessions.length > 0
    ) {
      setSelected(
        data.sessions[0].session_id,
      );
    }

    setMessage(
      data.sessions.length
        ? "Select a session"
        : "No recorded sessions yet",
    );
  }

  async function loadReport(
    sessionId: string,
    rebuild = false,
  ) {
    if (!sessionId) return;

    setLoading(true);
    setMessage(
      "Building grounded performance report...",
    );

    try {
      const response = await fetch(
        `${API}/api/sessions/`
        + `${encodeURIComponent(sessionId)}`
        + `/report?rebuild=${rebuild}`,
        {
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error(
          await response.text(),
        );
      }

      const reportData =
        (await response.json()) as PostRaceReport;

      setReport(reportData);

      const detailResponse = await fetch(
        `${API}/api/sessions/`
        + encodeURIComponent(sessionId),
        {
          cache: "no-store",
        },
      );

      if (detailResponse.ok) {
        const detail =
          (await detailResponse.json()) as {
            ai_report?: AIReport | null;
          };

        setAIReport(
          detail.ai_report || null,
        );
      }

      setMessage("Report ready");

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Report failed",
      );

      setReport(null);

    } finally {
      setLoading(false);
    }
  }

  async function runAIAnalysis() {
    if (!selected) return;

    setLoading(true);

    setMessage(
      "Retrieving race evidence "
      + "and generating analysis...",
    );

    try {
      const response = await fetch(
        `${API}/api/sessions/`
        + `${encodeURIComponent(selected)}`
        + "/analyze",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            question:
              question.trim()
              || undefined,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(
          await response.text(),
        );
      }

      const analysisData =
        (await response.json()) as AIReport;

      setAIReport(analysisData);

      setMessage(
        "AI/RAG analysis ready",
      );

    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Analysis failed",
      );

    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSessions().catch((error) => {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not load sessions",
      );
    });
  }, []);

  useEffect(() => {
    if (selected) {
      loadReport(selected).catch(
        () => undefined,
      );
    }
  }, [selected]);

  const summaryCards = useMemo(() => {
    const summary = report?.summary;

    if (!summary) return [];

    return [
      [
        "Finish",
        summary.finish_position
          ? `P${summary.finish_position}`
          : "--",
      ],
      [
        "Positions",
        summary.positions_gained === null
          ? "--"
          : (
              summary.positions_gained >= 0
                ? "+"
                : ""
            )
            + summary.positions_gained,
      ],
      [
        "Best lap",
        formatLap(summary.best_lap_s),
      ],
      [
        "Average",
        formatLap(summary.average_lap_s),
      ],
      [
        "Consistency",
        summary.lap_consistency_s === null
          ? "--"
          : (
              "±"
              + summary.lap_consistency_s
                .toFixed(3)
              + "s"
            ),
      ],
      [
        "Overtakes",
        summary.overtakes_detected,
      ],
      [
        "Incidents",
        summary.incidents_detected,
      ],
      [
        "Overlap",
        summary
          .brake_throttle_overlap_s
          .toFixed(1)
        + "s",
      ],
    ];
  }, [report]);

  return (
    <main className="reports-shell">
      <header className="reports-header">
        <div>
          <a
            href="/"
            className="reports-back"
          >
            ← Live dashboard
          </a>

          <h1>Post-race analysis</h1>

          <p>
            Saved sessions, lap pace,
            racecraft timeline, nearby-car
            comparison, and grounded RAG
            analysis.
          </p>
        </div>

        <button
          onClick={loadSessions}
          disabled={loading}
        >
          Refresh sessions
        </button>
      </header>

      <section className="reports-layout">
        <aside className="session-list panel">
          <div className="report-section-title">
            <h2>Sessions</h2>
            <span>{sessions.length}</span>
          </div>

          <div className="session-scroll">
            {sessions.map((session) => (
              <button
                key={session.session_id}
                className={
                  "session-item "
                  + (
                    selected
                    === session.session_id
                      ? "active"
                      : ""
                  )
                }
                onClick={() => {
                  setSelected(
                    session.session_id,
                  );
                }}
              >
                <strong>
                  {formatDate(
                    session.started_at,
                  )}
                </strong>

                <span>
                  Track{" "}
                  {session.track_id ?? "--"}
                  {" · "}
                  {session.status}
                </span>

                <small>
                  {session.finish_position
                    ? (
                        "P"
                        + session.finish_position
                      )
                    : "No finish"}
                  {" · "}
                  {session.recorded_samples}
                  {" samples"}
                </small>
              </button>
            ))}

            {sessions.length === 0 && (
              <p className="report-muted">
                Complete a simulator or game
                session first.
              </p>
            )}
          </div>
        </aside>

        <section className="report-content">
          <div className="report-toolbar panel">
            <div>
              <strong>
                {selected
                  || "No session selected"}
              </strong>

              <span>{message}</span>
            </div>

            <button
              disabled={
                !selected || loading
              }
              onClick={() => {
                loadReport(
                  selected,
                  true,
                );
              }}
            >
              Rebuild report
            </button>
          </div>

          {report && (
            <>
              <section className="report-summary-grid">
                {summaryCards.map(
                  ([label, value]) => (
                    <div
                      className="report-stat panel"
                      key={String(label)}
                    >
                      <span>{label}</span>
                      <strong>
                        {String(value)}
                      </strong>
                    </div>
                  ),
                )}
              </section>

              <section className="report-two-column">
                <div className="panel report-list-card">
                  <h2>What went well</h2>

                  <ul>
                    {report.strengths.map(
                      (item) => (
                        <li key={item}>
                          {item}
                        </li>
                      ),
                    )}
                  </ul>
                </div>

                <div className="panel report-list-card">
                  <h2>Areas to improve</h2>

                  <ul>
                    {report
                      .areas_to_improve
                      .map((item) => (
                        <li key={item}>
                          {item}
                        </li>
                      ))}
                  </ul>
                </div>
              </section>

              <section className="panel report-table-card">
                <div className="report-section-title">
                  <h2>Lap analysis</h2>

                  <span>
                    {report
                      .lap_analysis
                      .length}{" "}
                    laps
                  </span>
                </div>

                <div className="report-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Lap</th>
                        <th>Time</th>
                        <th>Delta</th>
                        <th>Valid</th>
                        <th>Position</th>
                        <th>Tyre</th>
                        <th>Age</th>
                      </tr>
                    </thead>

                    <tbody>
                      {report
                        .lap_analysis
                        .map((lap, index) => (
                          <tr
                            key={
                              String(
                                lap.lap_number,
                              )
                              + "-"
                              + index
                            }
                          >
                            <td>
                              {String(
                                lap.lap_number
                                ?? "--",
                              )}
                            </td>

                            <td>
                              {formatLap(
                                Number(
                                  lap.lap_time_s
                                  || 0,
                                ),
                              )}
                            </td>

                            <td>
                              {lap
                                .delta_to_best_s
                                === null
                                || lap
                                  .delta_to_best_s
                                  === undefined
                                ? "--"
                                : (
                                    "+"
                                    + Number(
                                      lap
                                        .delta_to_best_s,
                                    ).toFixed(3)
                                    + "s"
                                  )}
                            </td>

                            <td>
                              {lap.valid
                                ? "Yes"
                                : "No"}
                            </td>

                            <td>
                              {lap.position
                                ? (
                                    "P"
                                    + String(
                                      lap.position,
                                    )
                                  )
                                : "--"}
                            </td>

                            <td>
                              {String(
                                lap
                                  .tyre_compound
                                ?? "--",
                              )}
                            </td>

                            <td>
                              {String(
                                lap
                                  .tyre_age_laps
                                ?? "--",
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="report-two-column report-lower-grid">
                <div className="panel timeline-card">
                  <div className="report-section-title">
                    <h2>Race timeline</h2>

                    <span>
                      {report.timeline.length}
                    </span>
                  </div>

                  <div className="report-event-scroll">
                    {report.timeline.map(
                      (event) => (
                        <EventCard
                          key={event.id}
                          event={event}
                        />
                      ),
                    )}

                    {!report
                      .timeline
                      .length && (
                      <p className="report-muted">
                        No timeline events
                        were recorded.
                      </p>
                    )}
                  </div>
                </div>

                <div className="panel comparison-card">
                  <h2>Grid comparison</h2>

                  {(
                    [
                      "leader",
                      "ahead",
                      "player",
                      "behind",
                    ] as const
                  ).map((key) => {
                    const car =
                      report
                        .comparisons[key];

                    return (
                      <div
                        className={
                          "comparison-row "
                          + (
                            key === "player"
                              ? "player"
                              : ""
                          )
                        }
                        key={key}
                      >
                        <span>{key}</span>

                        <strong>
                          {car?.name
                            ? String(
                                car.name,
                              )
                            : "--"}
                        </strong>

                        <small>
                          {car?.position
                            ? (
                                "P"
                                + String(
                                  car.position,
                                )
                              )
                            : "--"}
                        </small>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="panel ai-report-card">
                <div className="report-section-title">
                  <div>
                    <h2>
                      LLM / RAG performance
                      review
                    </h2>

                    <p>
                      Grounded only in retrieved
                      session evidence.
                    </p>
                  </div>

                  <span>
                    {aiReport?.provider
                      || "not generated"}
                  </span>
                </div>

                <div className="ai-query-row">
                  <input
                    value={question}
                    onChange={(event) => {
                      setQuestion(
                        event.target.value,
                      );
                    }}
                    placeholder={
                      "Ask: Where did I lose "
                      + "positions, and what "
                      + "should I fix first?"
                    }
                    onKeyDown={(event) => {
                      if (
                        event.key
                        === "Enter"
                      ) {
                        runAIAnalysis();
                      }
                    }}
                  />

                  <button
                    disabled={
                      loading || !selected
                    }
                    onClick={
                      runAIAnalysis
                    }
                  >
                    Analyze session
                  </button>
                </div>

                {aiReport ? (
                  <>
                    {aiReport.llm_error && (
                      <div className="report-warning">
                        LLM unavailable;
                        showing grounded local
                        fallback:{" "}
                        {aiReport.llm_error}
                      </div>
                    )}

                    <pre className="ai-narrative">
                      {aiReport.narrative}
                    </pre>

                    <details>
                      <summary>
                        Retrieved evidence (
                        {
                          aiReport
                            .retrieved_context
                            .length
                        }
                        )
                      </summary>

                      <div className="retrieved-context">
                        {aiReport
                          .retrieved_context
                          .map((item) => (
                            <div key={item.id}>
                              <strong>
                                {item.kind}
                                {" · score "}
                                {item.score
                                  .toFixed(3)}
                              </strong>

                              <p>
                                {item.text}
                              </p>
                            </div>
                          ))}
                      </div>
                    </details>
                  </>
                ) : (
                  <p className="report-muted">
                    Run the analysis to generate
                    a grounded performance review.
                  </p>
                )}
              </section>
            </>
          )}
        </section>
      </section>
    </main>
  );
}