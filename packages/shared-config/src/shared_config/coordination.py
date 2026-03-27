from __future__ import annotations

import json
from typing import Any, Protocol

from .keys import CacheKeyFactory


class SupportsRedis(Protocol):
    def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> Any: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, *names: str) -> int: ...


class RedisCoordinator:
    def __init__(self, client: SupportsRedis, *, key_factory: CacheKeyFactory | None = None) -> None:
        self._client = client
        self._keys = key_factory or CacheKeyFactory()

    def acquire_session_lock(self, session_id: str, owner: str, *, ttl_seconds: int = 30) -> bool:
        return bool(self._client.set(self._keys.session_lock(session_id), owner, nx=True, ex=ttl_seconds))

    def release_session_lock(self, session_id: str) -> None:
        self._client.delete(self._keys.session_lock(session_id))

    def set_active_turn(self, session_id: str, payload: dict[str, Any], *, ttl_seconds: int = 300) -> None:
        self._client.set(self._keys.active_turn(session_id), json.dumps(payload), ex=ttl_seconds)

    def get_active_turn(self, session_id: str) -> dict[str, Any] | None:
        raw = self._client.get(self._keys.active_turn(session_id))
        return None if raw is None else json.loads(raw)

    def clear_active_turn(self, session_id: str) -> None:
        self._client.delete(self._keys.active_turn(session_id))

    def open_discussion_window(self, session_id: str, payload: dict[str, Any], *, ttl_seconds: int = 300) -> None:
        self._client.set(self._keys.discussion_window(session_id), json.dumps(payload), ex=ttl_seconds)

    def get_discussion_window(self, session_id: str) -> dict[str, Any] | None:
        raw = self._client.get(self._keys.discussion_window(session_id))
        return None if raw is None else json.loads(raw)

    def close_discussion_window(self, session_id: str) -> None:
        self._client.delete(self._keys.discussion_window(session_id))

    def set_visibility_snapshot(
        self,
        session_id: str,
        actor_id: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int = 120,
    ) -> None:
        self._client.set(
            self._keys.visibility_snapshot(session_id, actor_id),
            json.dumps(payload),
            ex=ttl_seconds,
        )

    def get_visibility_snapshot(self, session_id: str, actor_id: str) -> dict[str, Any] | None:
        raw = self._client.get(self._keys.visibility_snapshot(session_id, actor_id))
        return None if raw is None else json.loads(raw)

    def clear_visibility_snapshot(self, session_id: str, actor_id: str) -> None:
        self._client.delete(self._keys.visibility_snapshot(session_id, actor_id))
