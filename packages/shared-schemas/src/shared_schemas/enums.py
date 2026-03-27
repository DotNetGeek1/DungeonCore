from __future__ import annotations

from enum import StrEnum


class ActorRole(StrEnum):
    PLAYER = "player"
    NPC = "npc"
    ENEMY = "enemy"
    DM = "dm"


class ControllerType(StrEnum):
    AGENT = "agent"
    HUMAN = "human"
    OPERATOR = "operator"


class ScenePhase(StrEnum):
    SCENE_INTRO = "scene_intro"
    DISCUSSION = "discussion"
    ACTION_COMMIT = "action_commit"
    RESOLUTION = "resolution"
    NARRATION = "narration"
    REACTION = "reaction"
    TURN_END = "turn_end"


class MessageChannel(StrEnum):
    IN_CHARACTER = "in_character"
    TABLE_TALK = "table_talk"
    PRIVATE_WHISPER = "private_whisper"
    DM_NOTICE = "dm_notice"


class Visibility(StrEnum):
    PUBLIC = "public"
    PARTY = "party"
    PRIVATE = "private"
    DM_ONLY = "dm_only"


class MemoryType(StrEnum):
    OBSERVATION = "observation"
    BELIEF = "belief"
    GOAL = "goal"
    RELATIONSHIP = "relationship"
    SUMMARY = "summary"


class ActionType(StrEnum):
    ATTACK = "attack"
    MOVE = "move"
    MOVE_AND_ATTACK = "move_and_attack"
    DEFEND = "defend"
    INSPECT = "inspect"
    INTERACT = "interact"
    CAST_SPELL_BASIC = "cast_spell_basic"
    UPDATE_MAP = "update_map"


class EventType(StrEnum):
    SESSION_STARTED = "session.started"
    SCENE_STARTED = "scene.started"
    DISCUSSION_OPENED = "discussion.opened"
    DISCUSSION_CLOSED = "discussion.closed"
    MESSAGE_CREATED = "message.created"
    ACTION_PROPOSED = "action.proposed"
    ACTION_VALIDATED = "action.validated"
    ACTION_AWAITING_HUMAN = "action.awaiting_human"
    DICE_ROLLED = "dice.rolled"
    STATE_UPDATED = "state.updated"
    ACTION_RESOLVED = "action.resolved"
    NARRATION_EMITTED = "narration.emitted"
    TAKEOVER_CHANGED = "takeover.changed"
    TURN_ENDED = "turn.ended"
    MAP_UPDATED = "map.updated"


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class OperatorCommandType(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    TAKEOVER = "takeover"
    RELEASE_TAKEOVER = "release_takeover"


class ActionSubmissionSource(StrEnum):
    AGENT = "agent"
    HUMAN = "human"
