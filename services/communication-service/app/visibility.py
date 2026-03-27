from __future__ import annotations

from dataclasses import dataclass

from shared_schemas.enums import MessageChannel, Visibility, ActorRole
from shared_schemas.messages import TableMessage
from shared_schemas.state import GameState


@dataclass
class VisibilityResult:
    visible: bool
    reason: str = ""


class VisibilityRules:
    def can_see_message(
        self,
        message: TableMessage,
        viewer_id: str,
        state: GameState,
    ) -> VisibilityResult:
        if message.sender_id == viewer_id:
            return VisibilityResult(visible=True, reason="sender can always see own messages")

        match message.channel:
            case MessageChannel.IN_CHARACTER:
                return self._check_in_character(message, viewer_id, state)
            case MessageChannel.TABLE_TALK:
                return self._check_table_talk(message, viewer_id, state)
            case MessageChannel.PRIVATE_WHISPER:
                return self._check_private_whisper(message, viewer_id, state)
            case MessageChannel.DM_NOTICE:
                return self._check_dm_notice(message, viewer_id, state)
            case _:
                return VisibilityResult(visible=False, reason=f"unknown channel: {message.channel}")

    def _check_in_character(
        self,
        message: TableMessage,
        viewer_id: str,
        state: GameState,
    ) -> VisibilityResult:
        if message.visibility == Visibility.PUBLIC:
            return VisibilityResult(visible=True, reason="in_character public messages are visible to all")

        is_actor_in_scene = viewer_id in state.characters or viewer_id in state.npcs
        if is_actor_in_scene:
            return VisibilityResult(visible=True, reason="actor is in the scene")

        return VisibilityResult(visible=False, reason="viewer not in scene")

    def _check_table_talk(
        self,
        message: TableMessage,
        viewer_id: str,
        state: GameState,
    ) -> VisibilityResult:
        if message.visibility == Visibility.PUBLIC:
            is_player = viewer_id in state.characters
            if is_player:
                return VisibilityResult(visible=True, reason="player can see public table talk")

        if message.visibility == Visibility.PARTY:
            is_player = viewer_id in state.characters
            if is_player:
                return VisibilityResult(visible=True, reason="player can see party table talk")

        if viewer_id in message.recipient_ids:
            return VisibilityResult(visible=True, reason="viewer is explicit recipient")

        return VisibilityResult(visible=False, reason="table_talk not visible to non-players")

    def _check_private_whisper(
        self,
        message: TableMessage,
        viewer_id: str,
        state: GameState,
    ) -> VisibilityResult:
        if viewer_id in message.recipient_ids:
            return VisibilityResult(visible=True, reason="viewer is explicit recipient of whisper")

        return VisibilityResult(visible=False, reason="private whisper only visible to recipients")

    def _check_dm_notice(
        self,
        message: TableMessage,
        viewer_id: str,
        state: GameState,
    ) -> VisibilityResult:
        if viewer_id in message.recipient_ids:
            return VisibilityResult(visible=True, reason="viewer is recipient of DM notice")

        return VisibilityResult(visible=False, reason="DM notice only visible to recipients")

    def filter_visible_messages(
        self,
        messages: list[TableMessage],
        viewer_id: str,
        state: GameState,
    ) -> list[TableMessage]:
        return [m for m in messages if self.can_see_message(m, viewer_id, state).visible]


def get_visibility_rules() -> VisibilityRules:
    return VisibilityRules()
