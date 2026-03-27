from __future__ import annotations

from typing import Any

from shared_config.coordination import RedisCoordinator


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and name in self.storage:
            return False
        self.storage[name] = value
        return True

    def get(self, name: str) -> str | None:
        return self.storage.get(name)

    def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            if name in self.storage:
                deleted += 1
                del self.storage[name]
        return deleted


def test_session_lock_conflict_behavior() -> None:
    coordinator = RedisCoordinator(FakeRedis())

    assert coordinator.acquire_session_lock("session_001", "owner_a")
    assert not coordinator.acquire_session_lock("session_001", "owner_b")

    coordinator.release_session_lock("session_001")
    assert coordinator.acquire_session_lock("session_001", "owner_b")


def test_turn_discussion_and_visibility_cache_round_trip() -> None:
    coordinator = RedisCoordinator(FakeRedis())

    coordinator.set_active_turn("session_001", {"turn_number": 2, "active_actor_id": "char_fighter"})
    coordinator.open_discussion_window("session_001", {"open": True, "remaining_messages": 2})
    coordinator.set_visibility_snapshot("session_001", "char_fighter", {"known_entities": ["npc_goblin_shaman"]})

    assert coordinator.get_active_turn("session_001") == {"turn_number": 2, "active_actor_id": "char_fighter"}
    assert coordinator.get_discussion_window("session_001") == {"open": True, "remaining_messages": 2}
    assert coordinator.get_visibility_snapshot("session_001", "char_fighter") == {
        "known_entities": ["npc_goblin_shaman"]
    }

    coordinator.clear_active_turn("session_001")
    coordinator.close_discussion_window("session_001")
    coordinator.clear_visibility_snapshot("session_001", "char_fighter")

    assert coordinator.get_active_turn("session_001") is None
    assert coordinator.get_discussion_window("session_001") is None
    assert coordinator.get_visibility_snapshot("session_001", "char_fighter") is None
