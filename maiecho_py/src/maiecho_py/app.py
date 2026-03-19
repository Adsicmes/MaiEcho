from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from maiecho_py.internal.container import build_app_container
from maiecho_py.internal.router.api import build_api_router

__all__ = ["build_app_container", "create_app"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_app_container()
    app.state.container = container

    container.scheduler.start()
    yield

    container.scheduler.shutdown(wait=False)
    await container.scheduler.close_collectors()
    await container.providers.close()
    await container.llm.close()
    container.database.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MaiEcho Python",
        version="0.1.0",
        description="MaiEcho 的 Python 3.12 服务脚手架。",
        lifespan=lifespan,
    )
    app.include_router(build_api_router())
    return app
