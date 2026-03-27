from __future__ import annotations

import shared_schemas


def test_public_exports_are_available() -> None:
    assert hasattr(shared_schemas, "GameState")
    assert hasattr(shared_schemas, "PlayerTurn")
    assert hasattr(shared_schemas, "GameEvent")
    assert shared_schemas.SCHEMA_VERSION == "1.0.0"
