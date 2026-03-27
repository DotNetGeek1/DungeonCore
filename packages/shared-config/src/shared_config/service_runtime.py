from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

from .connections import check_postgres_health, check_rabbitmq_health, check_redis_health
from .settings import ServiceSettings


def build_health_payload(
    settings: ServiceSettings,
    *,
    include_model_fields: bool = False,
    dependency_checker: Callable[[ServiceSettings], dict[str, bool]] | None = None,
) -> dict[str, object]:
    checks = (
        dependency_checker(settings)
        if dependency_checker is not None
        else {
            "postgres": check_postgres_health(settings),
            "redis": check_redis_health(settings),
            "rabbitmq": check_rabbitmq_health(settings),
        }
    )
    payload: dict[str, object] = {
        "service": settings.service_name,
        "status": "ok" if all(checks.values()) else "degraded",
        "port": settings.port,
        "dependencies": checks,
        "message": "DungeonCore placeholder service is running.",
    }
    if include_model_fields:
        payload["model_provider"] = settings.model_provider
        payload["lmstudio_base_url"] = str(settings.lmstudio_base_url) if settings.lmstudio_base_url else ""
    return payload


def serve_placeholder(default_service_name: str, default_port: int, *, include_model_fields: bool = False) -> None:
    settings = ServiceSettings.for_service(default_service_name, default_port)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = build_health_payload(settings, include_model_fields=include_model_fields)
            payload = json.dumps(body).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            return

    HTTPServer(("0.0.0.0", settings.port), Handler).serve_forever()
