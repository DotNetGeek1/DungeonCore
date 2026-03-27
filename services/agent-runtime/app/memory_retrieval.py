from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal, Protocol

from shared_schemas.enums import MemoryType, Visibility
from shared_schemas.memory import MemoryEntry


# ---------------------------------------------------------------------------
# Memory Store Protocol + Implementations
# ---------------------------------------------------------------------------

class MemoryStore(Protocol):
    def get_by_actor(self, session_id: str, actor_id: str) -> list[MemoryEntry]: ...
    def save(self, memory: MemoryEntry) -> None: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._memories: dict[str, list[MemoryEntry]] = {}

    def _key(self, session_id: str, actor_id: str) -> str:
        return f"{session_id}:{actor_id}"

    def get_by_actor(self, session_id: str, actor_id: str) -> list[MemoryEntry]:
        key = self._key(session_id, actor_id)
        return self._memories.get(key, [])

    def save(self, memory: MemoryEntry) -> None:
        key = self._key(memory.session_id, memory.actor_id)
        if key not in self._memories:
            self._memories[key] = []
        self._memories[key].append(memory)

    def clear(self) -> None:
        self._memories.clear()


class PostgresMemoryStore:
    """Postgres-backed memory store. Queries the memory_entries table.

    Falls back to in-memory if the connection is unavailable.
    Schema expects: id, session_id, actor_id, memory_type, text,
    importance, tags (JSON array), created_at_turn, source_event_id,
    visibility.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn
        self._fallback = InMemoryMemoryStore()
        self._conn = None

    def _get_conn(self):
        if self._conn is not None:
            return self._conn
        if not self._dsn:
            return None
        try:
            import psycopg2
            self._conn = psycopg2.connect(self._dsn)
            return self._conn
        except Exception:
            return None

    def get_by_actor(self, session_id: str, actor_id: str) -> list[MemoryEntry]:
        conn = self._get_conn()
        if conn is None:
            return self._fallback.get_by_actor(session_id, actor_id)

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, session_id, actor_id, memory_type, text,
                              importance, tags, created_at_turn,
                              source_event_id, visibility
                       FROM memory_entries
                       WHERE session_id = %s AND actor_id = %s
                       ORDER BY created_at_turn DESC""",
                    (session_id, actor_id),
                )
                rows = cur.fetchall()
                return [self._row_to_entry(row) for row in rows]
        except Exception:
            return self._fallback.get_by_actor(session_id, actor_id)

    def save(self, memory: MemoryEntry) -> None:
        self._fallback.save(memory)

        conn = self._get_conn()
        if conn is None:
            return

        try:
            import json
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO memory_entries
                       (id, session_id, actor_id, memory_type, text,
                        importance, tags, created_at_turn,
                        source_event_id, visibility)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (
                        memory.id,
                        memory.session_id,
                        memory.actor_id,
                        memory.memory_type.value,
                        memory.text,
                        memory.importance,
                        json.dumps(memory.tags),
                        memory.created_at_turn,
                        memory.source_event_id,
                        memory.visibility.value,
                    ),
                )
            conn.commit()
        except Exception:
            pass

    def _row_to_entry(self, row: tuple) -> MemoryEntry:
        import json
        tags = row[6]
        if isinstance(tags, str):
            tags = json.loads(tags)
        return MemoryEntry(
            id=row[0],
            session_id=row[1],
            actor_id=row[2],
            memory_type=MemoryType(row[3]),
            text=row[4],
            importance=row[5],
            tags=tags or [],
            created_at_turn=row[7],
            source_event_id=row[8],
            visibility=Visibility(row[9]),
        )


# ---------------------------------------------------------------------------
# Four-Layer Memory Types
# ---------------------------------------------------------------------------

WORKING_MEMORY_TYPES = {MemoryType.OBSERVATION}
EPISODIC_MEMORY_TYPES = {MemoryType.OBSERVATION, MemoryType.SUMMARY}
SEMANTIC_MEMORY_TYPES = {MemoryType.BELIEF, MemoryType.RELATIONSHIP, MemoryType.GOAL}
PRIVATE_MEMORY_TYPES = {MemoryType.GOAL, MemoryType.BELIEF}


# ---------------------------------------------------------------------------
# Keyword-Based Semantic Relevance
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "not", "with", "from", "by", "as",
    "it", "this", "that", "they", "he", "she", "you", "we", "i", "my",
})


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]


def keyword_relevance(query_text: str, memory_text: str) -> float:
    """Simple keyword overlap relevance score in [0, 1]."""
    query_tokens = Counter(_tokenize(query_text))
    memory_tokens = Counter(_tokenize(memory_text))
    if not query_tokens or not memory_tokens:
        return 0.0
    overlap = sum((query_tokens & memory_tokens).values())
    total = sum(query_tokens.values())
    return min(1.0, overlap / max(total, 1))


# ---------------------------------------------------------------------------
# Retrieval Config + Scoring
# ---------------------------------------------------------------------------

@dataclass
class RetrievalConfig:
    max_results: int = 10
    min_importance: int = 1
    recency_weight: float = 0.25
    importance_weight: float = 0.45
    relevance_weight: float = 0.30


@dataclass
class ScoredMemory:
    memory: MemoryEntry
    score: float
    recency_score: float = 0.0
    importance_score: float = 0.0
    relevance_score: float = 0.0


class MemoryRetriever:
    def __init__(
        self,
        store: MemoryStore | None = None,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.store = store or InMemoryMemoryStore()
        self.config = config or RetrievalConfig()

    def retrieve(
        self,
        session_id: str,
        actor_id: str,
        current_turn: int,
        memory_types: list[MemoryType] | None = None,
        tags: list[str] | None = None,
        query_text: str = "",
    ) -> list[MemoryEntry]:
        all_memories = self.store.get_by_actor(session_id, actor_id)

        filtered = [
            m for m in all_memories
            if m.importance >= self.config.min_importance
        ]

        if memory_types:
            filtered = [m for m in filtered if m.memory_type in memory_types]

        if tags:
            filtered = [
                m for m in filtered
                if any(t in m.tags for t in tags)
            ]

        scored = self._score_memories(filtered, current_turn, query_text)
        scored.sort(key=lambda x: x.score, reverse=True)

        return [s.memory for s in scored[: self.config.max_results]]

    def retrieve_layered(
        self,
        session_id: str,
        actor_id: str,
        current_turn: int,
        query_text: str = "",
        working_limit: int = 3,
        episodic_limit: int = 3,
        semantic_limit: int = 2,
        private_limit: int = 2,
    ) -> list[MemoryEntry]:
        """Retrieve memories from all four layers, deduplicated and merged."""
        all_memories = self.store.get_by_actor(session_id, actor_id)

        working = [m for m in all_memories if m.memory_type in WORKING_MEMORY_TYPES]
        episodic = [m for m in all_memories if m.memory_type in EPISODIC_MEMORY_TYPES]
        semantic = [m for m in all_memories if m.memory_type in SEMANTIC_MEMORY_TYPES]
        private = [m for m in all_memories if m.visibility == Visibility.PRIVATE]

        seen_ids: set[str] = set()
        result: list[MemoryEntry] = []

        for layer_memories, limit in [
            (working, working_limit),
            (episodic, episodic_limit),
            (semantic, semantic_limit),
            (private, private_limit),
        ]:
            scored = self._score_memories(layer_memories, current_turn, query_text)
            scored.sort(key=lambda x: x.score, reverse=True)
            count = 0
            for sm in scored:
                if count >= limit:
                    break
                if sm.memory.id not in seen_ids:
                    seen_ids.add(sm.memory.id)
                    result.append(sm.memory)
                    count += 1

        return result

    def _score_memories(
        self,
        memories: list[MemoryEntry],
        current_turn: int,
        query_text: str = "",
    ) -> list[ScoredMemory]:
        if not memories:
            return []

        max_importance = 10

        scored = []
        for memory in memories:
            recency_score = 1.0 - ((current_turn - memory.created_at_turn) / max(current_turn, 1))
            recency_score = max(0.0, recency_score)

            importance_score = memory.importance / max_importance

            relevance_score = 0.0
            if query_text:
                relevance_score = keyword_relevance(query_text, memory.text)

            if query_text:
                total_score = (
                    self.config.recency_weight * recency_score
                    + self.config.importance_weight * importance_score
                    + self.config.relevance_weight * relevance_score
                )
            else:
                # Without query text, distribute relevance weight to others
                total_score = (
                    (self.config.recency_weight + self.config.relevance_weight / 2) * recency_score
                    + (self.config.importance_weight + self.config.relevance_weight / 2) * importance_score
                )

            scored.append(ScoredMemory(
                memory=memory,
                score=total_score,
                recency_score=recency_score,
                importance_score=importance_score,
                relevance_score=relevance_score,
            ))

        return scored

    def retrieve_by_type(
        self,
        session_id: str,
        actor_id: str,
        memory_type: MemoryType,
        current_turn: int,
    ) -> list[MemoryEntry]:
        return self.retrieve(
            session_id=session_id,
            actor_id=actor_id,
            current_turn=current_turn,
            memory_types=[memory_type],
        )

    def retrieve_recent(
        self,
        session_id: str,
        actor_id: str,
        current_turn: int,
        lookback_turns: int = 5,
    ) -> list[MemoryEntry]:
        all_memories = self.store.get_by_actor(session_id, actor_id)
        min_turn = current_turn - lookback_turns

        recent = [m for m in all_memories if m.created_at_turn >= min_turn]
        recent.sort(key=lambda m: m.created_at_turn, reverse=True)

        return recent[: self.config.max_results]


def get_memory_retriever(
    store: MemoryStore | None = None,
    config: RetrievalConfig | None = None,
) -> MemoryRetriever:
    return MemoryRetriever(store, config)
