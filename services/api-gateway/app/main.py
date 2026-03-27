from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
)
from shared_config.settings import ServiceSettings

from .routes import health, sessions, websocket


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: ServiceSettings = app.state.settings
    print(f"Starting {settings.service_name} on port {settings.port}")
    yield
    print(f"Shutting down {settings.service_name}")


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    if settings is None:
        settings = ServiceSettings.for_service("api-gateway", 8000)

    app = FastAPI(
        title="DungeonCore API Gateway",
        description="API Gateway for the DungeonCore multi-agent D&D engine",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.include_router(health.router, tags=["health"])
    app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
    app.include_router(websocket.router, tags=["websocket"])

    return app


def main() -> None:
    settings = ServiceSettings.for_service("api-gateway", 8000)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
