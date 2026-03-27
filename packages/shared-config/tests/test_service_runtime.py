from __future__ import annotations

from shared_config.service_runtime import build_health_payload
from shared_config.settings import ServiceSettings


def test_build_health_payload_with_dependency_checker() -> None:
    settings = ServiceSettings(service_name="api-gateway", port=8000)
    payload = build_health_payload(
        settings,
        dependency_checker=lambda _settings: {"postgres": True, "redis": True, "rabbitmq": False},
    )

    assert payload["service"] == "api-gateway"
    assert payload["status"] == "degraded"
    assert payload["dependencies"] == {"postgres": True, "redis": True, "rabbitmq": False}
