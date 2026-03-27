from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from shared_schemas.enums import MessageChannel
from shared_schemas.messages import TableMessage


@dataclass
class BudgetConfig:
    max_messages_per_discussion: int = 5
    max_message_length: int = 500
    max_messages_per_actor_per_discussion: int = 2
    channel_limits: dict[MessageChannel, int] = field(default_factory=lambda: {
        MessageChannel.IN_CHARACTER: 3,
        MessageChannel.TABLE_TALK: 5,
        MessageChannel.PRIVATE_WHISPER: 2,
        MessageChannel.DM_NOTICE: 10,
    })


@dataclass
class BudgetCheckResult:
    allowed: bool
    reason: str = ""
    remaining: int = 0


class BudgetEnforcer:
    def __init__(self, config: BudgetConfig | None = None) -> None:
        self.config = config or BudgetConfig()

    def check_message_budget(
        self,
        sender_id: str,
        channel: MessageChannel,
        text: str,
        existing_messages: list[TableMessage],
        discussion_id: str | None = None,
    ) -> BudgetCheckResult:
        if len(text) > self.config.max_message_length:
            return BudgetCheckResult(
                allowed=False,
                reason=f"Message exceeds max length of {self.config.max_message_length} characters",
                remaining=0,
            )

        discussion_messages = [
            m for m in existing_messages
            if discussion_id is None or getattr(m, 'discussion_id', None) == discussion_id
        ]

        if len(discussion_messages) >= self.config.max_messages_per_discussion:
            return BudgetCheckResult(
                allowed=False,
                reason=f"Discussion has reached max of {self.config.max_messages_per_discussion} messages",
                remaining=0,
            )

        actor_messages = [m for m in discussion_messages if m.sender_id == sender_id]
        if len(actor_messages) >= self.config.max_messages_per_actor_per_discussion:
            return BudgetCheckResult(
                allowed=False,
                reason=f"Actor has reached max of {self.config.max_messages_per_actor_per_discussion} messages per discussion",
                remaining=0,
            )

        channel_limit = self.config.channel_limits.get(channel, 3)
        channel_messages = [m for m in discussion_messages if m.channel == channel]
        if len(channel_messages) >= channel_limit:
            return BudgetCheckResult(
                allowed=False,
                reason=f"Channel {channel} has reached max of {channel_limit} messages",
                remaining=0,
            )

        remaining = min(
            self.config.max_messages_per_discussion - len(discussion_messages),
            self.config.max_messages_per_actor_per_discussion - len(actor_messages),
            channel_limit - len(channel_messages),
        )

        return BudgetCheckResult(
            allowed=True,
            reason="Message within budget",
            remaining=remaining,
        )

    def get_remaining_budget(
        self,
        sender_id: str,
        channel: MessageChannel,
        existing_messages: list[TableMessage],
    ) -> dict[str, int]:
        discussion_messages = existing_messages

        actor_messages = [m for m in discussion_messages if m.sender_id == sender_id]
        channel_messages = [m for m in discussion_messages if m.channel == channel]
        channel_limit = self.config.channel_limits.get(channel, 3)

        return {
            "total_remaining": self.config.max_messages_per_discussion - len(discussion_messages),
            "actor_remaining": self.config.max_messages_per_actor_per_discussion - len(actor_messages),
            "channel_remaining": channel_limit - len(channel_messages),
        }


def get_budget_enforcer(config: BudgetConfig | None = None) -> BudgetEnforcer:
    return BudgetEnforcer(config)
