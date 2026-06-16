from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.runtime import RaceEngineerRuntime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    runtime = RaceEngineerRuntime(settings)
    app.state.runtime = runtime
    runtime.start()
    try:
        yield
    finally:
        runtime.stop()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
