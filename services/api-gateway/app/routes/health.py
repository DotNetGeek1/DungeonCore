from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
)
from shared_config.settings import ServiceSettings

router = APIRouter()


class DependencyStatus(BaseModel):
    postgres: bool
    redis: bool
    rabbitmq: bool


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok", "degraded"]
    port: int
    dependencies: DependencyStatus


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    settings: ServiceSettings = request.app.state.settings

    deps = DependencyStatus(
        postgres=check_postgres_health(settings),
        redis=check_redis_health(settings),
        rabbitmq=check_rabbitmq_health(settings),
    )

    all_healthy = deps.postgres and deps.redis and deps.rabbitmq

    return HealthResponse(
        service=settings.service_name,
        status="ok" if all_healthy else "degraded",
        port=settings.port,
        dependencies=deps,
    )
