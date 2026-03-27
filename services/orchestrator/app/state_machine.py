from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, TypeAlias
import uuid

from shared_schemas.enums import ScenePhase
from shared_schemas.state import GameState


class TransitionError(Exception):
    pass


@dataclass
class PhaseContext:
    session_id: str
    state: GameState
    trace_id: str
    correlation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, object] = field(default_factory=dict)


PhaseHandler: TypeAlias = Callable[[PhaseContext], PhaseContext]


ALLOWED_TRANSITIONS: dict[ScenePhase, list[ScenePhase]] = {
    ScenePhase.SCENE_INTRO: [ScenePhase.DISCUSSION],
    ScenePhase.DISCUSSION: [ScenePhase.ACTION_COMMIT],
    ScenePhase.ACTION_COMMIT: [ScenePhase.RESOLUTION],
    ScenePhase.RESOLUTION: [ScenePhase.NARRATION],
    ScenePhase.NARRATION: [ScenePhase.REACTION],
    ScenePhase.REACTION: [ScenePhase.TURN_END],
    ScenePhase.TURN_END: [ScenePhase.SCENE_INTRO, ScenePhase.DISCUSSION],
}


class StateMachine:
    def __init__(self) -> None:
        self._handlers: dict[ScenePhase, PhaseHandler] = {}

    def register_handler(self, phase: ScenePhase, handler: PhaseHandler) -> None:
        self._handlers[phase] = handler

    def get_handler(self, phase: ScenePhase) -> PhaseHandler | None:
        return self._handlers.get(phase)

    def can_transition(self, from_phase: ScenePhase, to_phase: ScenePhase) -> bool:
        allowed = ALLOWED_TRANSITIONS.get(from_phase, [])
        return to_phase in allowed

    def validate_transition(self, from_phase: ScenePhase, to_phase: ScenePhase) -> None:
        if not self.can_transition(from_phase, to_phase):
            raise TransitionError(
                f"Invalid transition from {from_phase} to {to_phase}. "
                f"Allowed: {ALLOWED_TRANSITIONS.get(from_phase, [])}"
            )

    def next_phase(self, current_phase: ScenePhase) -> ScenePhase | None:
        allowed = ALLOWED_TRANSITIONS.get(current_phase, [])
        if not allowed:
            return None
        return allowed[0]

    async def execute_phase(self, ctx: PhaseContext) -> PhaseContext:
        current_phase = ctx.state.scene.phase
        handler = self._handlers.get(current_phase)

        if handler is None:
            return ctx

        return handler(ctx)

    async def transition_to(self, ctx: PhaseContext, target_phase: ScenePhase) -> PhaseContext:
        current_phase = ctx.state.scene.phase
        self.validate_transition(current_phase, target_phase)

        new_scene = ctx.state.scene.model_copy(update={"phase": target_phase})
        new_turn = ctx.state.turn.model_copy(update={"phase": target_phase})
        new_state = ctx.state.model_copy(update={"scene": new_scene, "turn": new_turn})

        return PhaseContext(
            session_id=ctx.session_id,
            state=new_state,
            trace_id=ctx.trace_id,
            correlation_id=ctx.correlation_id,
            created_at=ctx.created_at,
            metadata=ctx.metadata.copy(),
        )


def create_phase_context(
    session_id: str,
    state: GameState,
    trace_id: str | None = None,
    correlation_id: str | None = None,
) -> PhaseContext:
    return PhaseContext(
        session_id=session_id,
        state=state,
        trace_id=trace_id or str(uuid.uuid4()),
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
