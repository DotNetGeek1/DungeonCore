from __future__ import annotations


class CacheKeyFactory:
    def session_lock(self, session_id: str) -> str:
        return f"session:{session_id}:lock"

    def active_turn(self, session_id: str) -> str:
        return f"session:{session_id}:turn"

    def discussion_window(self, session_id: str) -> str:
        return f"session:{session_id}:discussion"

    def visibility_snapshot(self, session_id: str, actor_id: str) -> str:
        return f"session:{session_id}:visibility:{actor_id}"
