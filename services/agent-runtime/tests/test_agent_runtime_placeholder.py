from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for path in (
    REPO_ROOT / ".codex_deps",
    REPO_ROOT / "packages" / "shared-config" / "src",
    REPO_ROOT / "packages" / "shared-schemas" / "src",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared_config.service_runtime import build_health_payload
from shared_config.settings import ServiceSettings


def test_placeholder() -> None:
    payload = build_health_payload(
        ServiceSettings(service_name="agent-runtime", port=8002),
        include_model_fields=True,
        dependency_checker=lambda _settings: {"postgres": True, "redis": False, "rabbitmq": True},
    )
    assert payload["model_provider"] == "lmstudio"
