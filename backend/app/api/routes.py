from __future__ import annotations

import asyncio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter()


def runtime(request: Request):
    return request.app.state.runtime


@router.get("/")
def root(request: Request):
    rt = runtime(request)
    return {"name": rt.settings.app_name, "docs": "/docs", "ws": "/ws/live"}


@router.get("/api/health")
def health(request: Request):
    return runtime(request).health()


@router.get("/api/state")
def state(request: Request):
    return runtime(request).state.snapshot().to_dict()


@router.get("/api/messages")
def messages(request: Request):
    return runtime(request).state.messages()


@router.post("/api/reset")
def reset(request: Request):
    runtime(request).reset()
    return {"ok": True}


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


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    rt = websocket.app.state.runtime
    try:
        while True:
            await websocket.send_json(rt.state.snapshot().to_dict())
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
    except RuntimeError:
        return