from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

from shared_config.persistence import (
    ActionRecordRepository,
    EventRepository,
    MemoryEntryRepository,
    MessageRepository,
    SessionRepository,
    StateSnapshotRepository,
)
from shared_schemas.examples import (
    build_example_action_proposed_event,
    build_example_action_record,
    build_example_create_session_response,
    build_example_discussion_opened_event,
    build_example_memory_entry,
    build_example_state_snapshot_record,
    build_example_table_message,
)


def test_alembic_upgrade_creates_phase2_tables(tmp_path) -> None:
    database_path = tmp_path / "phase2.sqlite"
    config = Config(str(Path("infra/alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database_path}", future=True))
    table_names = set(inspector.get_table_names())

    assert "campaigns" in table_names
    assert "sessions" in table_names
    assert "events" in table_names
    assert "memory_entries" in table_names
    assert "action_records" in table_names


def test_repositories_persist_and_query_timeline_data(tmp_path) -> None:
    database_path = tmp_path / "repo.sqlite"
    config = Config(str(Path("infra/alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}", future=True)

    session_repo = SessionRepository(engine)
    event_repo = EventRepository(engine)
    message_repo = MessageRepository(engine)
    memory_repo = MemoryEntryRepository(engine)
    action_repo = ActionRecordRepository(engine)
    snapshot_repo = StateSnapshotRepository(engine)

    session_repo.create_campaign("campaign_blackstone", "Blackstone", {"theme": "bridge"})
    session_repo.create_scene("scene_bridge", "campaign_blackstone", "Blackstone Bridge", {"phase": "discussion"})
    session_repo.create_session(build_example_create_session_response().model_dump(mode="json"))

    event_repo.append(build_example_discussion_opened_event().model_dump(mode="json"))
    event_repo.append(build_example_action_proposed_event().model_dump(mode="json"))
    message_repo.append(build_example_table_message().model_dump(mode="json"))
    memory_repo.append(build_example_memory_entry().model_dump(mode="json"))
    action_repo.append(build_example_action_record().model_dump(mode="json"))
    snapshot_repo.append(build_example_state_snapshot_record().model_dump(mode="json"))

    session_payload = session_repo.get_session("session_001")
    timeline = event_repo.list_for_session("session_001")
    visible_messages = message_repo.list_visible("session_001", recipient_id="char_cleric")
    memories = memory_repo.list_for_actor("session_001", "char_fighter")
    actions = action_repo.list_for_session("session_001")
    latest_snapshot = snapshot_repo.get_latest("session_001")

    assert session_payload is not None
    assert session_payload["session"]["session_id"] == "session_001"
    assert [event["event_type"] for event in timeline] == ["discussion.opened", "action.proposed"]
    assert visible_messages[0]["id"] == "msg_001"
    assert memories[0]["id"] == "memory_001"
    assert actions[0]["id"] == "action_record_001"
    assert latest_snapshot is not None
    assert latest_snapshot["scene_id"] == "scene_bridge"
