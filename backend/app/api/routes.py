from __future__ import annotations

import asyncio
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


def runtime(request: Request):
    return request.app.state.runtime


@router.get("/")
def root(request: Request):
    engineer = runtime(request)

    return {
        "name": engineer.settings.app_name,
        "docs": "/docs",
        "ws": "/ws/live",
        "reports": "/api/sessions",
    }


@router.get("/api/health")
def health(request: Request):
    return runtime(request).health()


@router.get("/api/state")
def state(request: Request):
    return (
        runtime(request)
        .state
        .snapshot()
        .to_dict()
    )


@router.get("/api/messages")
def messages(request: Request):
    return (
        runtime(request)
        .state
        .messages()
    )


@router.get("/api/events")
def events(request: Request):
    return (
        runtime(request)
        .state
        .events()
    )


@router.post("/api/reset")
def reset(request: Request):
    return runtime(request).reset()


@router.post("/api/voice")
def voice(
    request: Request,
    enabled: bool,
):
    runtime(request).set_voice_enabled(
        enabled
    )

    return {
        "ok": True,
        "voice_enabled": enabled,
    }


@router.post("/api/voice/test")
def voice_test(request: Request):
    return runtime(request).test_voice()


@router.post("/api/coaching")
def coaching(
    request: Request,
    enabled: bool,
):
    runtime(request).set_coaching_enabled(
        enabled
    )

    return {
        "ok": True,
        "coaching_enabled": enabled,
    }


@router.get("/api/sessions")
def sessions(request: Request):
    return {
        "sessions": (
            runtime(request)
            .recorder
            .list_sessions()
        )
    }


@router.get(
    "/api/sessions/{session_id}"
)
def session_detail(
    request: Request,
    session_id: str,
    telemetry_limit: int = Query(
        default=0,
        ge=0,
        le=100_000,
    ),
):
    try:
        return (
            runtime(request)
            .recorder
            .get_session_bundle(
                session_id,
                telemetry_limit=(
                    telemetry_limit
                ),
            )
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/sessions/{session_id}/telemetry"
)
def session_telemetry(
    request: Request,
    session_id: str,
    limit: int = Query(
        default=0,
        ge=0,
        le=100_000,
    ),
):
    try:
        telemetry = (
            runtime(request)
            .recorder
            .get_telemetry(
                session_id,
                limit,
            )
        )

        return {
            "session_id": session_id,
            "telemetry": telemetry,
        }

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/sessions/{session_id}/finalize"
)
def finalize_session(
    request: Request,
    session_id: str,
):
    engineer = runtime(request)

    active = (
        engineer
        .recorder
        .active_session_id
    )

    if active != session_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Session {session_id!r} "
                "is not the active recording"
            ),
        )

    metadata = (
        engineer
        .recorder
        .finalize_current(
            "manual_finalize",
            engineer.state.snapshot(),
        )
    )

    engineer.state.set_recording_state(
        None,
        False,
    )

    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail="No active recording",
        )

    report = (
        engineer
        .post_race
        .build_report(
            session_id,
            save=True,
        )
    )

    return {
        "ok": True,
        "metadata": metadata,
        "report": report,
    }


@router.get(
    "/api/sessions/{session_id}/report"
)
def session_report(
    request: Request,
    session_id: str,
    rebuild: bool = False,
):
    engineer = runtime(request)

    try:
        if not rebuild:
            bundle = (
                engineer
                .recorder
                .get_session_bundle(
                    session_id
                )
            )

            if bundle.get("report"):
                return bundle["report"]

        return (
            engineer
            .post_race
            .build_report(
                session_id,
                save=True,
            )
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/api/sessions/{session_id}/analyze"
)
def analyze_session(
    request: Request,
    session_id: str,
    payload: (
        dict[str, Any] | None
    ) = Body(default=None),
):
    question = str(
        (payload or {}).get("question")
        or ""
    ).strip() or None

    try:
        return (
            runtime(request)
            .rag
            .analyze(
                session_id,
                question=question,
            )
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Analysis failed: {exc}"
            ),
        ) from exc


@router.websocket("/ws/live")
async def websocket_live(
    websocket: WebSocket,
):
    await websocket.accept()

    engineer = (
        websocket
        .app
        .state
        .runtime
    )

    try:
        while True:
            snapshot = (
                engineer
                .state
                .snapshot()
                .to_dict()
            )

            await websocket.send_json(
                snapshot
            )

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        return

    except RuntimeError:
        return