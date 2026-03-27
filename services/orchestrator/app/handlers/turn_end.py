from __future__ import annotations

from shared_schemas.enums import ScenePhase

from ..state_machine import PhaseContext


def handle_turn_end(ctx: PhaseContext) -> PhaseContext:
    characters = list(ctx.state.characters.values())
    current_actor_id = ctx.state.scene.active_actor_id

    next_actor_id: str | None = None
    if characters:
        if current_actor_id:
            current_index = next(
                (i for i, c in enumerate(characters) if c.actor_id == current_actor_id),
                -1,
            )
            next_index = (current_index + 1) % len(characters)
        else:
            next_index = 0
        next_actor_id = characters[next_index].actor_id

    new_turn_number = ctx.state.turn.turn_number + 1
    new_round = ctx.state.turn.round_number

    if next_actor_id and characters and next_actor_id == characters[0].actor_id:
        new_round += 1

    new_turn = ctx.state.turn.model_copy(
        update={
            "turn_number": new_turn_number,
            "round_number": new_round,
            "active_actor_id": next_actor_id,
            "phase": ScenePhase.DISCUSSION,
            "remaining_discussion_messages": ctx.state.turn.max_discussion_messages,
        }
    )
    new_scene = ctx.state.scene.model_copy(
        update={
            "turn_number": new_turn_number,
            "active_actor_id": next_actor_id,
            "phase": ScenePhase.DISCUSSION,
        }
    )
    new_state = ctx.state.model_copy(update={"turn": new_turn, "scene": new_scene})

    return PhaseContext(
        session_id=ctx.session_id,
        state=new_state,
        trace_id=ctx.trace_id,
        correlation_id=ctx.correlation_id,
        created_at=ctx.created_at,
        metadata=ctx.metadata,
    )
