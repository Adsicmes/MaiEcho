from __future__ import annotations

from fastapi import APIRouter

from maiecho_py.internal.controller.analysis_controller import router as analysis_router
from maiecho_py.internal.controller.collector_controller import (
    router as collector_router,
)
from maiecho_py.internal.controller.song_controller import router as song_router
from maiecho_py.internal.controller.status_controller import router as status_router


def build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(status_router)
    router.include_router(song_router)
    router.include_router(collector_router)
    router.include_router(analysis_router)
    return router
