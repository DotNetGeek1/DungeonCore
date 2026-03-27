from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from shared_schemas.enums import MessageChannel, ScenePhase, Visibility
from shared_schemas.messages import TableMessage
from shared_schemas.state import GameState

from .budgets import BudgetCheckResult, BudgetEnforcer, get_budget_enforcer
from .visibility import VisibilityRules, get_visibility_rules


@dataclass
class CreateMessageRequest:
    session_id: str
    scene_id: str
    turn_number: int
    phase: ScenePhase
    channel: MessageChannel
    sender_id: str
    text: str
    recipient_ids: list[str] = field(default_factory=list)
    visibility: Visibility | None = None


@dataclass
class CreateMessageResult:
    success: bool
    message: TableMessage | None = None
    error: str | None = None


class MessageStore(Protocol):
    def save(self, message: TableMessage) -> None: ...
    def get_by_session(self, session_id: str) -> list[TableMessage]: ...
    def get_by_session_and_turn(self, session_id: str, turn_number: int) -> list[TableMessage]: ...


class InMemoryMessageStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[TableMessage]] = {}

    def save(self, message: TableMessage) -> None:
        if message.session_id not in self._messages:
            self._messages[message.session_id] = []
        self._messages[message.session_id].append(message)

    def get_by_session(self, session_id: str) -> list[TableMessage]:
        return self._messages.get(session_id, [])

    def get_by_session_and_turn(self, session_id: str, turn_number: int) -> list[TableMessage]:
        return [
            m for m in self._messages.get(session_id, [])
            if m.turn_number == turn_number
        ]

    def clear(self) -> None:
        self._messages.clear()


class MessageService:
    def __init__(
        self,
        store: MessageStore | None = None,
        budget_enforcer: BudgetEnforcer | None = None,
        visibility_rules: VisibilityRules | None = None,
    ) -> None:
        self.store = store or InMemoryMessageStore()
        self.budget_enforcer = budget_enforcer or get_budget_enforcer()
        self.visibility_rules = visibility_rules or get_visibility_rules()

    def _determine_visibility(self, channel: MessageChannel, explicit: Visibility | None) -> Visibility:
        if explicit is not None:
            return explicit

        match channel:
            case MessageChannel.IN_CHARACTER:
                return Visibility.PUBLIC
            case MessageChannel.TABLE_TALK:
                return Visibility.PARTY
            case MessageChannel.PRIVATE_WHISPER:
                return Visibility.PRIVATE
            case MessageChannel.DM_NOTICE:
                return Visibility.PRIVATE
            case _:
                return Visibility.PUBLIC

    def create_message(self, request: CreateMessageRequest) -> CreateMessageResult:
        existing = self.store.get_by_session_and_turn(request.session_id, request.turn_number)

        budget_check = self.budget_enforcer.check_message_budget(
            sender_id=request.sender_id,
            channel=request.channel,
            text=request.text,
            existing_messages=existing,
        )

        if not budget_check.allowed:
            return CreateMessageResult(
                success=False,
                error=budget_check.reason,
            )

        visibility = self._determine_visibility(request.channel, request.visibility)

        message = TableMessage(
            id=str(uuid.uuid4()),
            session_id=request.session_id,
            scene_id=request.scene_id,
            turn_number=request.turn_number,
            phase=request.phase,
            channel=request.channel,
            sender_id=request.sender_id,
            recipient_ids=request.recipient_ids,
            visibility=visibility,
            text=request.text,
            created_at=datetime.now(timezone.utc),
        )

        self.store.save(message)

        return CreateMessageResult(
            success=True,
            message=message,
        )

    def get_visible_messages(
        self,
        session_id: str,
        viewer_id: str,
        state: GameState,
        turn_number: int | None = None,
    ) -> list[TableMessage]:
        if turn_number is not None:
            messages = self.store.get_by_session_and_turn(session_id, turn_number)
        else:
            messages = self.store.get_by_session(session_id)

        return self.visibility_rules.filter_visible_messages(messages, viewer_id, state)

    def get_all_messages(self, session_id: str) -> list[TableMessage]:
        return self.store.get_by_session(session_id)

    def get_remaining_budget(
        self,
        session_id: str,
        turn_number: int,
        sender_id: str,
        channel: MessageChannel,
    ) -> dict[str, int]:
        existing = self.store.get_by_session_and_turn(session_id, turn_number)
        return self.budget_enforcer.get_remaining_budget(sender_id, channel, existing)


def get_message_service(
    store: MessageStore | None = None,
    budget_enforcer: BudgetEnforcer | None = None,
    visibility_rules: VisibilityRules | None = None,
) -> MessageService:
    return MessageService(store, budget_enforcer, visibility_rules)
