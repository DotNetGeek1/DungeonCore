from __future__ import annotations

import json

from shared_schemas.schema_export import export_schema_bundle, write_schema_bundle


def test_schema_bundle_contains_discriminated_unions() -> None:
    bundle = export_schema_bundle()

    assert "GameEvent" in bundle
    assert "discriminator" in bundle["GameEvent"]
    assert bundle["GameEvent"]["discriminator"]["propertyName"] == "event_type"
    assert "PlayerTurn" in bundle


def test_schema_bundle_can_be_written(tmp_path) -> None:
    path = write_schema_bundle(tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == "shared-schemas.json"
    assert "GameState" in written
