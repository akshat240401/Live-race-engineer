from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

router = APIRouter()


def runtime(request: Request):  # noqa: ANN201
    return request.app.state.runtime


@router.get("/")
def root(request: Request):
    engineer = runtime(request)
    return {
        "name": engineer.settings.app_name,
        "docs": "/docs",
        "ws": "/ws/live",
        "reports": "/api/sessions",
        "radio": "/api/radio/status",
    }


@router.get("/api/health")
def health(request: Request):
    return runtime(request).health()


@router.get("/api/state")
def state(request: Request):
    return runtime(request).state.snapshot().to_dict()


@router.get("/api/messages")
def messages(request: Request):
    return runtime(request).state.messages()


@router.get("/api/events")
def events(request: Request):
    return runtime(request).state.events()


@router.post("/api/reset")
def reset(request: Request):
    return runtime(request).reset()


@router.post("/api/voice")
def voice(request: Request, enabled: bool):
    runtime(request).set_voice_enabled(enabled)
    return {"ok": True, "voice_enabled": enabled}


@router.post("/api/voice/test")
def voice_test(request: Request):
    return runtime(request).test_voice()


@router.post("/api/coaching")
def coaching(request: Request, enabled: bool):
    runtime(request).set_coaching_enabled(enabled)
    return {"ok": True, "coaching_enabled": enabled}


# ---------------------------------------------------------------------------
# Hands-free live radio
# ---------------------------------------------------------------------------


@router.get("/api/radio/status")
def radio_status(request: Request):
    return runtime(request).live_radio.status()


@router.get("/api/strategy/live")
def live_strategy(request: Request):
    return runtime(request).live_radio.decision(recompute=False)


@router.post("/api/strategy/recompute")
def recompute_strategy(request: Request):
    return runtime(request).live_radio.decision(recompute=True)


@router.get("/api/radio/transcript")
def radio_transcript(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
):
    return {
        "items": runtime(request).live_radio.transcript(limit),
    }


@router.get("/api/radio/devices")
def radio_devices(request: Request):
    try:
        return {
            "devices": runtime(request).live_radio.list_input_devices(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/radio/enabled")
def radio_enabled(request: Request, enabled: bool):
    return runtime(request).live_radio.set_enabled(enabled)


@router.post("/api/radio/mode")
def radio_mode(request: Request, mode: str):
    try:
        return runtime(request).live_radio.set_mode(mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Mode must be minimal, race, or coaching",
        ) from exc


@router.post("/api/radio/listen")
def radio_listen(request: Request, acknowledge: bool = True):
    return runtime(request).live_radio.open_conversation(acknowledge=acknowledge)


@router.post("/api/radio/calibrate")
def radio_calibrate(
    request: Request,
    duration_s: float = Query(default=5.0, ge=2.0, le=15.0),
):
    try:
        return runtime(request).live_radio.calibrate_noise(duration_s)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/radio/quiet")
def radio_quiet(request: Request, quiet: bool = True):
    if quiet:
        return runtime(request).live_radio.quiet_updates()
    return runtime(request).live_radio.resume_updates()


@router.post("/api/radio/repeat")
def radio_repeat(request: Request, speak: bool = True):
    return runtime(request).live_radio.repeat_last(speak=speak)


@router.post("/api/radio/test")
def radio_test(
    request: Request,
    payload: dict[str, Any] | None = Body(default=None),
):
    data = payload or {}
    text = str(data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Body must include non-empty text")
    speak = bool(data.get("speak", True))
    return runtime(request).live_radio.process_text(
        text,
        source="api",
        bypass_wake=True,
        speak=speak,
    )


# ---------------------------------------------------------------------------
# Session recording and reports
# ---------------------------------------------------------------------------


@router.get("/api/sessions")
def sessions(request: Request):
    return {"sessions": runtime(request).recorder.list_sessions()}


@router.get("/api/sessions/{session_id}")
def session_detail(
    request: Request,
    session_id: str,
    telemetry_limit: int = Query(default=0, ge=0, le=100_000),
):
    try:
        return runtime(request).recorder.get_session_bundle(
            session_id,
            telemetry_limit=telemetry_limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/sessions/{session_id}/radio")
def session_radio(
    request: Request,
    session_id: str,
    limit: int = Query(default=0, ge=0, le=10_000),
):
    try:
        directory = runtime(request).recorder.session_directory(session_id)
        path = directory / "radio.jsonl"
        rows: list[dict[str, Any]] = []
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if limit > 0:
            rows = rows[-limit:]
        return {"session_id": session_id, "items": rows}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/sessions/{session_id}/telemetry")
def session_telemetry(
    request: Request,
    session_id: str,
    limit: int = Query(default=0, ge=0, le=100_000),
):
    try:
        telemetry = runtime(request).recorder.get_telemetry(session_id, limit)
        return {"session_id": session_id, "telemetry": telemetry}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/sessions/{session_id}/finalize")
def finalize_session(request: Request, session_id: str):
    engineer = runtime(request)
    active = engineer.recorder.active_session_id
    if active != session_id:
        raise HTTPException(
            status_code=409,
            detail=f"Session {session_id!r} is not the active recording",
        )
    metadata = engineer.recorder.finalize_current(
        "manual_finalize",
        engineer.state.snapshot(),
    )
    engineer.state.set_recording_state(None, False)
    if metadata is None:
        raise HTTPException(status_code=404, detail="No active recording")
    report = engineer.post_race.build_report(session_id, save=True)
    return {"ok": True, "metadata": metadata, "report": report}


@router.get("/api/sessions/{session_id}/report")
def session_report(
    request: Request,
    session_id: str,
    rebuild: bool = False,
):
    engineer = runtime(request)
    try:
        if not rebuild:
            bundle = engineer.recorder.get_session_bundle(session_id)
            if bundle.get("report"):
                return bundle["report"]
        return engineer.post_race.build_report(session_id, save=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/sessions/{session_id}/analyze")
def analyze_session(
    request: Request,
    session_id: str,
    payload: dict[str, Any] | None = Body(default=None),
):
    question = str((payload or {}).get("question") or "").strip() or None
    try:
        return runtime(request).rag.analyze(session_id, question=question)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    engineer = websocket.app.state.runtime
    try:
        while True:
            snapshot = engineer.state.snapshot().to_dict()
            await websocket.send_json(snapshot)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
    except RuntimeError:
        return
