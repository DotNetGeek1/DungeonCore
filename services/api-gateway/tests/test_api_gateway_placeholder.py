from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[3] / "packages" / "shared-schemas" / "src"
CONFIG_SRC = Path(__file__).resolve().parents[3] / "packages" / "shared-config" / "src"
DEPS_SRC = Path(__file__).resolve().parents[3] / ".codex_deps"

for path in (DEPS_SRC, CONFIG_SRC, PACKAGE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared_config.service_runtime import build_health_payload
from shared_config.settings import ServiceSettings
from shared_schemas import GameState, PlayerTurn
from shared_schemas.examples import EXAMPLE_GAME_STATE, EXAMPLE_PLAYER_TURN


def test_placeholder_service_can_import_shared_contracts() -> None:
    state = GameState.model_validate(EXAMPLE_GAME_STATE)
    turn = PlayerTurn.model_validate(EXAMPLE_PLAYER_TURN)

    assert state.scene.scene_id == "scene_bridge"
    assert turn.action is not None


def test_placeholder_service_uses_shared_health_payload() -> None:
    settings = ServiceSettings(service_name="api-gateway", port=8000)
    payload = build_health_payload(
        settings,
        dependency_checker=lambda _settings: {"postgres": True, "redis": True, "rabbitmq": True},
    )

    assert payload["service"] == "api-gateway"
    assert payload["status"] == "ok"
