from __future__ import annotations

from shared_schemas.enums import ScenePhase

from ..state_machine import PhaseContext


def handle_reaction(ctx: PhaseContext) -> PhaseContext:
    new_scene = ctx.state.scene.model_copy(update={"phase": ScenePhase.TURN_END})
    new_turn = ctx.state.turn.model_copy(update={"phase": ScenePhase.TURN_END})
    new_state = ctx.state.model_copy(update={"scene": new_scene, "turn": new_turn})

    return PhaseContext(
        session_id=ctx.session_id,
        state=new_state,
        trace_id=ctx.trace_id,
        correlation_id=ctx.correlation_id,
        created_at=ctx.created_at,
        metadata=ctx.metadata,
    )
