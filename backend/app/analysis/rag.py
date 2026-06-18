from __future__ import annotations

from collections import Counter
import json
import math
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.analysis.post_race import (
    PostRaceAnalyzer,
)
from app.recording.session_recorder import (
    SessionRecorder,
)


TOKEN_RE = re.compile(
    r"[a-zA-Z0-9_.+-]+"
)


def _tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1
    ]


def _cosine(
    query: Counter[str],
    document: Counter[str],
) -> float:
    if not query or not document:
        return 0.0

    dot = sum(
        query[token]
        * document.get(token, 0)
        for token in query
    )

    query_norm = math.sqrt(
        sum(
            value * value
            for value in query.values()
        )
    )

    document_norm = math.sqrt(
        sum(
            value * value
            for value in document.values()
        )
    )

    if not query_norm or not document_norm:
        return 0.0

    return dot / (
        query_norm * document_norm
    )


class RAGReportService:
    def __init__(
        self,
        recorder: SessionRecorder,
        analyzer: PostRaceAnalyzer,
        *,
        llm_enabled: bool = False,
        llm_base_url: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
        llm_timeout_s: int = 45,
    ) -> None:
        self.recorder = recorder
        self.analyzer = analyzer
        self.llm_enabled = llm_enabled
        self.llm_base_url = (
            llm_base_url.rstrip("/")
        )
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.llm_timeout_s = llm_timeout_s

    def analyze(
        self,
        session_id: str,
        question: str | None = None,
    ) -> dict[str, Any]:
        report = self.analyzer.build_report(
            session_id,
            save=True,
        )

        documents = self._build_documents(
            report
        )

        query = question or (
            "Analyze race performance, braking, "
            "throttle application, tyre management, "
            "pace consistency, racecraft, incidents, "
            "position changes, strengths, and the "
            "highest-priority improvements."
        )

        retrieved = self._retrieve(
            documents,
            query,
            top_k=12,
        )

        provider = "local-rag-fallback"
        error: str | None = None

        if (
            self.llm_enabled
            and self.llm_base_url
            and self.llm_model
        ):
            try:
                narrative = (
                    self._call_compatible_llm(
                        query,
                        report,
                        retrieved,
                    )
                )
                provider = "configured-llm"

            except Exception as exc:
                error = str(exc)
                narrative = (
                    self._fallback_narrative(
                        report,
                        retrieved,
                    )
                )
        else:
            narrative = (
                self._fallback_narrative(
                    report,
                    retrieved,
                )
            )

        result = {
            "session_id": session_id,
            "question": query,
            "provider": provider,
            "llm_error": error,
            "narrative": narrative,
            "retrieved_context": retrieved,
            "grounded_summary": report["summary"],
        }

        self.recorder.save_report(
            session_id,
            result,
            ai=True,
        )

        return result

    @staticmethod
    def _build_documents(
        report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        documents: list[
            dict[str, Any]
        ] = []

        summary = report.get(
            "summary",
            {},
        )

        documents.append({
            "id": "session-summary",
            "kind": "summary",
            "text": (
                "Session summary: "
                + json.dumps(
                    summary,
                    ensure_ascii=False,
                )
            ),
            "data": summary,
        })

        for lap in report.get(
            "lap_analysis",
            [],
        ):
            documents.append({
                "id": (
                    f"lap-"
                    f"{lap.get('lap_number')}"
                ),
                "kind": "lap",
                "text": (
                    f"Lap {lap.get('lap_number')}: "
                    f"time {lap.get('lap_time_s')} "
                    "seconds, delta to best "
                    f"{lap.get('delta_to_best_s')} "
                    f"seconds, valid {lap.get('valid')}, "
                    f"position {lap.get('position')}, "
                    f"tyre {lap.get('tyre_compound')}, "
                    "tyre age "
                    f"{lap.get('tyre_age_laps')} laps."
                ),
                "data": lap,
            })

        for event in report.get(
            "timeline",
            [],
        ):
            documents.append({
                "id": (
                    f"event-{event.get('id')}"
                ),
                "kind": "event",
                "text": (
                    f"Lap {event.get('lap_number')} "
                    f"event {event.get('event_type')}: "
                    f"{event.get('title')}. "
                    f"{event.get('description')}. "
                    f"Data {event.get('data')}"
                ),
                "data": event,
            })

        for message in report.get(
            "coaching_messages",
            [],
        ):
            documents.append({
                "id": (
                    f"message-"
                    f"{message.get('id')}"
                ),
                "kind": "coaching",
                "text": (
                    f"Coaching "
                    f"{message.get('category')} "
                    f"{message.get('severity')}: "
                    f"{message.get('title')}. "
                    f"{message.get('message')}. "
                    f"Evidence "
                    f"{message.get('evidence')}"
                ),
                "data": message,
            })

        for label, value in (
            report.get(
                "comparisons",
                {},
            ).items()
        ):
            if value:
                documents.append({
                    "id": (
                        f"comparison-{label}"
                    ),
                    "kind": "comparison",
                    "text": (
                        "Classification comparison "
                        f"{label}: "
                        + json.dumps(
                            value,
                            ensure_ascii=False,
                        )
                    ),
                    "data": value,
                })

        return documents

    @staticmethod
    def _retrieve(
        documents: list[dict[str, Any]],
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        query_vector = Counter(
            _tokens(query)
        )

        scored: list[
            tuple[
                float,
                dict[str, Any],
            ]
        ] = []

        for document in documents:
            document_vector = Counter(
                _tokens(
                    str(
                        document.get(
                            "text",
                            "",
                        )
                    )
                )
            )

            score = _cosine(
                query_vector,
                document_vector,
            )

            if document.get("kind") == "event":
                score += 0.04

            if document.get("kind") == "summary":
                score += 0.08

            scored.append(
                (
                    score,
                    document,
                )
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            {
                "id": document["id"],
                "kind": document["kind"],
                "score": round(score, 4),
                "text": document["text"],
            }
            for score, document
            in scored[:top_k]
        ]

    def _call_compatible_llm(
        self,
        question: str,
        report: dict[str, Any],
        retrieved: list[
            dict[str, Any]
        ],
    ) -> str:
        endpoint = self.llm_base_url

        if not endpoint.endswith(
            "/chat/completions"
        ):
            endpoint += "/chat/completions"

        system_prompt = (
            "You are a concise motorsport "
            "performance engineer. Use only the "
            "supplied race evidence. Never invent "
            "corners, opponents, lap events, or "
            "causes. Clearly separate observed "
            "facts from inferences. Return: "
            "Executive summary, What went well, "
            "Where time was lost, Racecraft and "
            "incidents, and three priorities."
        )

        user_prompt = (
            f"QUESTION:\n{question}\n\n"
            "STRUCTURED SUMMARY:\n"
            f"{json.dumps(report.get('summary', {}), indent=2)}"
            "\n\nRETRIEVED EVIDENCE:\n"
            f"{json.dumps(retrieved, indent=2)}"
        )

        payload = {
            "model": self.llm_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.llm_api_key:
            headers["Authorization"] = (
                f"Bearer {self.llm_api_key}"
            )

        request = Request(
            endpoint,
            data=json.dumps(payload).encode(
                "utf-8"
            ),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.llm_timeout_s,
            ) as response:
                result = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

        except HTTPError as exc:
            body = (
                exc.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            raise RuntimeError(
                f"LLM HTTP {exc.code}: "
                f"{body[:400]}"
            ) from exc

        except URLError as exc:
            raise RuntimeError(
                "LLM connection failed: "
                f"{exc.reason}"
            ) from exc

        choices = result.get("choices") or []

        if not choices:
            raise RuntimeError(
                "LLM response did not "
                "contain choices"
            )

        content = (
            choices[0]
            .get("message", {})
            .get("content")
        )

        if (
            not isinstance(content, str)
            or not content.strip()
        ):
            raise RuntimeError(
                "LLM response did not "
                "contain text"
            )

        return content.strip()

    @staticmethod
    def _fallback_narrative(
        report: dict[str, Any],
        retrieved: list[
            dict[str, Any]
        ],
    ) -> str:
        summary = report.get(
            "summary",
            {},
        )

        strengths = report.get(
            "strengths",
            [],
        )

        improvements = report.get(
            "areas_to_improve",
            [],
        )

        start = summary.get(
            "start_position"
        )

        finish = summary.get(
            "finish_position"
        )

        best = summary.get(
            "best_lap_s"
        )

        average = summary.get(
            "average_lap_s"
        )

        if start and finish:
            position_text = (
                f"Started P{start} and "
                f"finished P{finish}."
            )
        else:
            position_text = (
                "A complete start/finish "
                "classification was not available."
            )

        lines = [
            "## Executive summary",
            (
                f"{position_text} "
                f"Best valid lap: "
                f"{best if best is not None else '--'}s; "
                f"average valid lap: "
                f"{average if average is not None else '--'}s. "
                "The report is grounded in "
                f"{summary.get('recorded_samples', 0)} "
                "telemetry samples."
            ),
            "",
            "## What went well",
        ]

        lines.extend(
            f"- {item}"
            for item in strengths
        )

        lines.extend([
            "",
            "## Highest-priority improvements",
        ])

        lines.extend(
            f"- {item}"
            for item in improvements[:4]
        )

        lines.extend([
            "",
            "## Retrieved race evidence",
        ])

        for item in retrieved[:6]:
            lines.append(
                f"- {item['text']}"
            )

        lines.extend([
            "",
            "## Next-session targets",
            (
                "1. Pick one repeatable braking "
                "reference and compare the next "
                "five valid laps."
            ),
            (
                "2. Keep brake and throttle "
                "phases separated through corner "
                "entry and rotation."
            ),
            (
                "3. Review any incident or "
                "position-loss event together "
                "with the preceding telemetry window."
            ),
        ])

        return "\n".join(lines)