from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request

from maiecho_py.internal.container import AppContainer
from maiecho_py.internal.status.schemas import SystemStatusResponse

router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatusResponse)
def get_status(request: Request) -> SystemStatusResponse:
    container = cast(AppContainer, request.app.state.container)
    return container.status_service.get_system_status()
