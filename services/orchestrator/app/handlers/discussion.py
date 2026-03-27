from __future__ import annotations

from shared_schemas.enums import ScenePhase

from ..state_machine import PhaseContext


def handle_discussion(ctx: PhaseContext) -> PhaseContext:
    new_turn = ctx.state.turn.model_copy(
        update={
            "phase": ScenePhase.ACTION_COMMIT,
            "discussion_open": False,
        }
    )
    new_scene = ctx.state.scene.model_copy(update={"phase": ScenePhase.ACTION_COMMIT})
    new_state = ctx.state.model_copy(update={"turn": new_turn, "scene": new_scene})

    return PhaseContext(
        session_id=ctx.session_id,
        state=new_state,
        trace_id=ctx.trace_id,
        correlation_id=ctx.correlation_id,
        created_at=ctx.created_at,
        metadata=ctx.metadata,
    )
