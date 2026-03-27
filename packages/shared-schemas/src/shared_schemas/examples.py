from __future__ import annotations

from datetime import datetime

from .actions import PlayerTurn
from .api import (
    ActionSubmissionRequest,
    ActionSubmissionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GetEventHistoryResponse,
    GetSessionStateResponse,
    GetVisibleMessagesResponse,
    OperatorCommandResponse,
    SessionSummary,
    WebSocketEventEnvelope,
)
from .context import AgentContext, AgentIdentity, CommunicationBudget
from .enums import (
    ActionSubmissionSource,
    ActionType,
    ActorRole,
    ControllerType,
    MessageChannel,
    OperatorCommandType,
    ScenePhase,
    SessionStatus,
    Visibility,
)
from .events import (
    ActionProposedEvent,
    ActionProposedPayload,
    ActionResolvedEvent,
    ActionResolvedPayload,
    ActionValidatedEvent,
    ActionValidatedPayload,
    DiceRollRecord,
    DiscussionOpenedEvent,
    DiscussionWindowPayload,
    MessageCreatedEvent,
    MessageCreatedPayload,
    NarrationEmittedEvent,
    NarrationEmittedPayload,
    SessionStartedEvent,
    SessionStartedPayload,
    StatePatchRecord,
    StateUpdatedEvent,
    StateUpdatedPayload,
    TurnEndedEvent,
    TurnEndedPayload,
)
from .memory import MemoryEntry
from .messages import TableMessage
from .persistence import ActionRecord, EventHistoryQuery, StateSnapshotRecord
from .state import (
    CharacterState,
    GameState,
    NpcState,
    ObjectiveState,
    Position,
    SceneState,
    TurnState,
    VisibilityScope,
)

EXAMPLE_TIMESTAMP = datetime(2026, 3, 24, 18, 30, 0)


def build_example_game_state() -> GameState:
    return GameState(
        campaign_id="campaign_blackstone",
        session_id="session_001",
        scene=SceneState(
            scene_id="scene_bridge",
            name="Blackstone Bridge",
            summary="The party faces goblin raiders on a narrow bridge.",
            phase=ScenePhase.DISCUSSION,
            turn_number=1,
            active_actor_id="char_fighter",
            location_name="North Bridge",
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id="char_fighter",
            phase=ScenePhase.DISCUSSION,
            discussion_open=True,
            max_discussion_messages=3,
            remaining_discussion_messages=2,
        ),
        characters={
            "char_fighter": CharacterState(
                actor_id="char_fighter",
                name="Ser Joren",
                role=ActorRole.PLAYER,
                hp=19,
                max_hp=24,
                ac=17,
                initiative=14,
                controller=ControllerType.AGENT,
                character_class="fighter",
                player_slot="player_1",
                position=Position(x=4, y=4, node_id="B4", zone_id="bridge"),
            ),
        },
        npcs={
            "npc_goblin_shaman": NpcState(
                actor_id="npc_goblin_shaman",
                name="Goblin Shaman",
                role=ActorRole.ENEMY,
                hp=12,
                max_hp=12,
                ac=13,
                initiative=11,
                disposition="hostile",
                behavior_tag="ranged_caster",
                position=Position(x=8, y=4, node_id="B8", zone_id="bridge"),
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
        },
        objectives=[
            ObjectiveState(
                objective_id="obj_hold_bridge",
                label="Hold the bridge",
                status="active",
                summary="Prevent the raiders from crossing into town.",
            ),
        ],
        flags={"bridge_on_fire": False, "fog_density": "light"},
    )


def build_example_table_message() -> TableMessage:
    return TableMessage(
        id="msg_001",
        session_id="session_001",
        scene_id="scene_bridge",
        turn_number=1,
        phase=ScenePhase.DISCUSSION,
        channel=MessageChannel.TABLE_TALK,
        sender_id="char_fighter",
        recipient_ids=["char_cleric"],
        visibility=Visibility.PARTY,
        text="Focus the shaman first.",
        created_at=EXAMPLE_TIMESTAMP,
    )


def build_example_player_turn() -> PlayerTurn:
    return PlayerTurn(
        thought="The shaman is the biggest threat.",
        speech="Steel yourselves. I strike now.",
        table_talk="Pin the shaman down.",
        action={
            "type": ActionType.MOVE_AND_ATTACK,
            "movement_path": ["B4", "B5", "B6"],
            "target_id": "npc_goblin_shaman",
        },
    )


def build_example_memory_entry() -> MemoryEntry:
    return MemoryEntry(
        id="memory_001",
        session_id="session_001",
        actor_id="char_fighter",
        memory_type="summary",
        text="The shaman resisted radiant damage in the chapel.",
        importance=8,
        tags=["goblin", "resistance"],
        created_at_turn=0,
        source_event_id="event_000",
        visibility=Visibility.PRIVATE,
    )


def build_example_action_proposed_event() -> ActionProposedEvent:
    return ActionProposedEvent(
        id="event_002",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=ActionProposedPayload(
            actor_id="char_fighter",
            turn=build_example_player_turn(),
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_scene_started_event():
    from .events import SceneStartedEvent, SceneStartedPayload

    return SceneStartedEvent(
        id="event_scene_001",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_scene_001",
        correlation_id="corr_scene_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=SceneStartedPayload(
            scene_id="scene_bridge",
            scene_name="Blackstone Bridge",
            phase=ScenePhase.SCENE_INTRO,
            active_actor_id="char_fighter",
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_agent_context() -> AgentContext:
    return AgentContext(
        session_id="session_001",
        identity=AgentIdentity(
            agent_id="agent_player_fighter",
            actor_id="char_fighter",
            role=ActorRole.PLAYER,
            name="Ser Joren",
            goals=["Protect allies", "Hold the line"],
        ),
        scene_summary="The bridge is crowded and the goblin shaman is exposed.",
        visible_state=build_example_game_state(),
        recent_events=[build_example_action_proposed_event()],
        recent_messages=[build_example_table_message()],
        memories=[build_example_memory_entry()],
        allowed_actions=[
            ActionType.ATTACK,
            ActionType.MOVE,
            ActionType.MOVE_AND_ATTACK,
            ActionType.DEFEND,
        ],
        communication_budget=CommunicationBudget(
            max_messages=3,
            remaining_messages=2,
            max_message_length=280,
        ),
    )


def build_example_session_started_event() -> SessionStartedEvent:
    state = build_example_game_state()
    return SessionStartedEvent(
        id="event_001",
        session_id="session_001",
        turn_number=0,
        trace_id="trace_bootstrap",
        correlation_id="corr_bootstrap",
        created_at=EXAMPLE_TIMESTAMP,
        payload=SessionStartedPayload(
            session_id="session_001",
            campaign_id="campaign_blackstone",
            started_by="operator_director",
            initial_state=state,
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_action_validated_event() -> ActionValidatedEvent:
    turn = build_example_player_turn()
    assert turn.action is not None
    return ActionValidatedEvent(
        id="event_003",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=ActionValidatedPayload(
            actor_id="char_fighter",
            valid=True,
            normalized_action=turn.action,
            errors=[],
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_discussion_opened_event() -> DiscussionOpenedEvent:
    return DiscussionOpenedEvent(
        id="event_004",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=DiscussionWindowPayload(
            scene_id="scene_bridge",
            active_actor_id="char_fighter",
            max_messages=3,
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_discussion_closed_event():
    from .events import DiscussionClosedEvent, DiscussionWindowPayload

    return DiscussionClosedEvent(
        id="event_004_closed",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=DiscussionWindowPayload(
            scene_id="scene_bridge",
            active_actor_id="char_fighter",
            max_messages=3,
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_message_created_event() -> MessageCreatedEvent:
    return MessageCreatedEvent(
        id="event_005",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=MessageCreatedPayload(
            message=build_example_table_message(),
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_state_updated_event() -> StateUpdatedEvent:
    return StateUpdatedEvent(
        id="event_006",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=StateUpdatedPayload(
            state=build_example_game_state(),
            reason="attack resolved",
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_dice_rolled_event():
    from .events import DiceRollRecord, DiceRolledEvent, DiceRolledPayload

    return DiceRolledEvent(
        id="event_006_roll",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=DiceRolledPayload(
            actor_id="char_fighter",
            action_type="attack",
            rolls=[
                DiceRollRecord(
                    die="d20",
                    value=15,
                    modifier=3,
                    total=18,
                    created_at=EXAMPLE_TIMESTAMP,
                )
            ],
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_action_resolved_event() -> ActionResolvedEvent:
    return ActionResolvedEvent(
        id="event_006_resolved",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=ActionResolvedPayload(
            actor_id="char_fighter",
            action_type="attack",
            success=True,
            description="Ser Joren strikes the goblin shaman for 8 damage.",
            dice_rolls=[
                DiceRollRecord(
                    die="d20",
                    value=17,
                    modifier=5,
                    total=22,
                    created_at=EXAMPLE_TIMESTAMP,
                ),
                DiceRollRecord(
                    die="d8",
                    value=6,
                    modifier=2,
                    total=8,
                    created_at=EXAMPLE_TIMESTAMP,
                ),
            ],
            state_patches=[
                StatePatchRecord(
                    patch_type="damage",
                    target_id="npc_goblin_shaman",
                    field="hp",
                    old_value=12,
                    new_value=4,
                    created_at=EXAMPLE_TIMESTAMP,
                ),
            ],
            hit=True,
            damage=8,
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_narration_emitted_event() -> NarrationEmittedEvent:
    return NarrationEmittedEvent(
        id="event_007",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=NarrationEmittedPayload(
            narrator_id="dm_001",
            text="Joren surges across the bridge and drives the goblin shaman back.",
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_turn_ended_event() -> TurnEndedEvent:
    return TurnEndedEvent(
        id="event_008",
        session_id="session_001",
        turn_number=1,
        trace_id="trace_turn_001",
        correlation_id="corr_turn_001",
        created_at=EXAMPLE_TIMESTAMP,
        payload=TurnEndedPayload(
            actor_id="char_fighter",
            next_actor_id="char_cleric",
            phase=ScenePhase.TURN_END,
            created_at=EXAMPLE_TIMESTAMP,
        ),
    )


def build_example_create_session_request() -> CreateSessionRequest:
    return CreateSessionRequest(
        campaign_id="campaign_blackstone",
        scene_id="scene_bridge",
        player_character_ids=["char_fighter", "char_cleric"],
        npc_ids=["npc_goblin_shaman"],
        seed=7,
    )


def build_example_create_session_response() -> CreateSessionResponse:
    return CreateSessionResponse(
        session=SessionSummary(
            session_id="session_001",
            campaign_id="campaign_blackstone",
            scene_id="scene_bridge",
            status=SessionStatus.CREATED,
        ),
        state=build_example_game_state(),
    )


def build_example_get_session_state_response() -> GetSessionStateResponse:
    return GetSessionStateResponse(
        session_id="session_001",
        state=build_example_game_state(),
    )


def build_example_get_event_history_response() -> GetEventHistoryResponse:
    return GetEventHistoryResponse(
        session_id="session_001",
        events=[
            build_example_session_started_event(),
            build_example_discussion_opened_event(),
            build_example_action_proposed_event(),
        ],
        next_cursor="cursor_002",
    )


def build_example_get_visible_messages_response() -> GetVisibleMessagesResponse:
    return GetVisibleMessagesResponse(
        session_id="session_001",
        messages=[build_example_table_message()],
    )


def build_example_operator_command_response() -> OperatorCommandResponse:
    return OperatorCommandResponse(
        session_id="session_001",
        command_type=OperatorCommandType.PAUSE,
        accepted=True,
        status=SessionStatus.PAUSED,
        event=build_example_message_created_event(),
    )


def build_example_action_submission_request() -> ActionSubmissionRequest:
    return ActionSubmissionRequest(
        actor_id="char_fighter",
        source=ActionSubmissionSource.AGENT,
        turn=build_example_player_turn(),
    )


def build_example_action_submission_response() -> ActionSubmissionResponse:
    turn = build_example_player_turn()
    assert turn.action is not None
    return ActionSubmissionResponse(
        session_id="session_001",
        accepted=True,
        action_status="validated",
        normalized_action=turn.action,
    )


def build_example_event_history_query() -> EventHistoryQuery:
    return EventHistoryQuery(session_id="session_001", limit=25, event_type="action.proposed")


def build_example_state_snapshot_record() -> StateSnapshotRecord:
    return StateSnapshotRecord(
        id="snapshot_001",
        session_id="session_001",
        scene_id="scene_bridge",
        turn_number=1,
        active_actor_id="char_fighter",
        state=build_example_game_state(),
        created_at=EXAMPLE_TIMESTAMP,
    )


def build_example_action_record() -> ActionRecord:
    turn = build_example_player_turn()
    return ActionRecord(
        id="action_record_001",
        session_id="session_001",
        actor_id="char_fighter",
        turn_number=1,
        action_type="move_and_attack",
        status="validated",
        source="agent",
        event_id="event_003",
        normalized_action=turn.action,
        created_at=EXAMPLE_TIMESTAMP,
    )


def build_example_websocket_event_envelope() -> WebSocketEventEnvelope:
    return WebSocketEventEnvelope(
        session_id="session_001",
        sequence_number=5,
        event=build_example_narration_emitted_event(),
    )


EXAMPLE_GAME_STATE = build_example_game_state().model_dump(mode="json")
EXAMPLE_TABLE_MESSAGE = build_example_table_message().model_dump(mode="json")
EXAMPLE_PLAYER_TURN = build_example_player_turn().model_dump(mode="json")
EXAMPLE_MEMORY_ENTRY = build_example_memory_entry().model_dump(mode="json")
EXAMPLE_AGENT_CONTEXT = build_example_agent_context().model_dump(mode="json")
EXAMPLE_EVENTS = {
    "session_started": build_example_session_started_event().model_dump(mode="json"),
    "scene_started": build_example_scene_started_event().model_dump(mode="json"),
    "discussion_opened": build_example_discussion_opened_event().model_dump(mode="json"),
    "discussion_closed": build_example_discussion_closed_event().model_dump(mode="json"),
    "message_created": build_example_message_created_event().model_dump(mode="json"),
    "action_proposed": build_example_action_proposed_event().model_dump(mode="json"),
    "action_validated": build_example_action_validated_event().model_dump(mode="json"),
    "dice_rolled": build_example_dice_rolled_event().model_dump(mode="json"),
    "action_resolved": build_example_action_resolved_event().model_dump(mode="json"),
    "state_updated": build_example_state_updated_event().model_dump(mode="json"),
    "narration_emitted": build_example_narration_emitted_event().model_dump(mode="json"),
    "turn_ended": build_example_turn_ended_event().model_dump(mode="json"),
}
EXAMPLE_API_PAYLOADS = {
    "create_session_request": build_example_create_session_request().model_dump(mode="json"),
    "create_session_response": build_example_create_session_response().model_dump(mode="json"),
    "get_session_state_response": build_example_get_session_state_response().model_dump(mode="json"),
    "get_event_history_response": build_example_get_event_history_response().model_dump(mode="json"),
    "get_visible_messages_response": build_example_get_visible_messages_response().model_dump(mode="json"),
    "operator_command_response": build_example_operator_command_response().model_dump(mode="json"),
    "action_submission_request": build_example_action_submission_request().model_dump(mode="json"),
    "action_submission_response": build_example_action_submission_response().model_dump(mode="json"),
    "websocket_event_envelope": build_example_websocket_event_envelope().model_dump(mode="json"),
    "event_history_query": build_example_event_history_query().model_dump(mode="json"),
}
EXAMPLE_PERSISTENCE_PAYLOADS = {
    "state_snapshot_record": build_example_state_snapshot_record().model_dump(mode="json"),
    "action_record": build_example_action_record().model_dump(mode="json"),
}
