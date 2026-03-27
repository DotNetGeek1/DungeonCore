from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_schemas.enums import ActorRole


@dataclass
class ModelPolicy:
    """Configuration for a specific model invocation.

    Defines provider, model, and generation parameters that can be
    customized per-agent or per-role.
    Azure GPT-4.1 supports up to 16K output tokens.
    """

    provider: str = "lmstudio"
    model_name: str = "local-model"
    temperature: float = 0.4
    max_tokens: int = 8192
    timeout_seconds: float = 120.0

    def with_overrides(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> ModelPolicy:
        """Create a new policy with specified overrides."""
        return ModelPolicy(
            provider=self.provider,
            model_name=self.model_name,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else self.timeout_seconds,
        )


@dataclass
class ModelPolicyDefaults:
    """Default model policies for different agent roles.

    These can be loaded from environment or configuration files.
    Azure GPT-4.1 supports up to 16K output tokens, so we can be generous.
    """

    dm: ModelPolicy = field(default_factory=lambda: ModelPolicy(
        temperature=0.7,
        max_tokens=8192,
    ))
    player: ModelPolicy = field(default_factory=lambda: ModelPolicy(
        temperature=0.4,
        max_tokens=8192,
    ))
    narrator: ModelPolicy = field(default_factory=lambda: ModelPolicy(
        temperature=0.5,
        max_tokens=4096,
    ))
    default: ModelPolicy = field(default_factory=lambda: ModelPolicy(
        max_tokens=8192,
    ))


class ModelPolicyConfig:
    """Manages model policies with role-based defaults and per-agent overrides."""

    def __init__(
        self,
        defaults: ModelPolicyDefaults | None = None,
        agent_overrides: dict[str, ModelPolicy] | None = None,
    ) -> None:
        self._defaults = defaults or ModelPolicyDefaults()
        self._agent_overrides: dict[str, ModelPolicy] = agent_overrides or {}

    @property
    def defaults(self) -> ModelPolicyDefaults:
        return self._defaults

    def get_policy_for_role(self, role: ActorRole) -> ModelPolicy:
        """Get the default policy for a given actor role."""
        from shared_schemas.enums import ActorRole

        role_map = {
            ActorRole.DM: self._defaults.dm,
            ActorRole.PLAYER: self._defaults.player,
            ActorRole.NPC: self._defaults.default,
        }
        return role_map.get(role, self._defaults.default)

    def get_policy_for_agent(
        self,
        agent_id: str,
        role: ActorRole | None = None,
    ) -> ModelPolicy:
        """Get the policy for a specific agent, falling back to role defaults.

        Args:
            agent_id: Unique identifier for the agent
            role: Actor role for fallback if no agent override exists

        Returns:
            ModelPolicy for the agent
        """
        if agent_id in self._agent_overrides:
            return self._agent_overrides[agent_id]

        if role is not None:
            return self.get_policy_for_role(role)

        return self._defaults.default

    def set_agent_override(self, agent_id: str, policy: ModelPolicy) -> None:
        """Set a custom policy for a specific agent."""
        self._agent_overrides[agent_id] = policy

    def remove_agent_override(self, agent_id: str) -> bool:
        """Remove the custom policy for an agent. Returns True if one existed."""
        if agent_id in self._agent_overrides:
            del self._agent_overrides[agent_id]
            return True
        return False

    def list_agent_overrides(self) -> list[str]:
        """Return list of agent IDs with custom policies."""
        return list(self._agent_overrides.keys())

    @classmethod
    def from_settings(
        cls,
        provider: str = "lmstudio",
        dm_model: str | None = None,
        dm_temperature: float | None = None,
        player_model: str | None = None,
        player_temperature: float | None = None,
        narrator_model: str | None = None,
        narrator_temperature: float | None = None,
        default_model: str = "local-model",
        default_temperature: float = 0.4,
        default_max_tokens: int = 8192,
        default_timeout: float = 120.0,
    ) -> ModelPolicyConfig:
        """Create a ModelPolicyConfig from settings values.

        This factory method allows building the config from environment variables
        or other configuration sources.
        Azure GPT-4.1 supports up to 16K output tokens.
        """
        base_policy = ModelPolicy(
            provider=provider,
            model_name=default_model,
            temperature=default_temperature,
            max_tokens=default_max_tokens,
            timeout_seconds=default_timeout,
        )

        dm_policy = ModelPolicy(
            provider=provider,
            model_name=dm_model or default_model,
            temperature=dm_temperature if dm_temperature is not None else 0.7,
            max_tokens=8192,
            timeout_seconds=default_timeout,
        )

        player_policy = ModelPolicy(
            provider=provider,
            model_name=player_model or default_model,
            temperature=player_temperature if player_temperature is not None else 0.4,
            max_tokens=8192,
            timeout_seconds=default_timeout,
        )

        narrator_policy = ModelPolicy(
            provider=provider,
            model_name=narrator_model or default_model,
            temperature=narrator_temperature if narrator_temperature is not None else 0.5,
            max_tokens=4096,
            timeout_seconds=default_timeout,
        )

        defaults = ModelPolicyDefaults(
            dm=dm_policy,
            player=player_policy,
            narrator=narrator_policy,
            default=base_policy,
        )

        return cls(defaults=defaults)


def get_model_policy_config() -> ModelPolicyConfig:
    """Factory function to create a default ModelPolicyConfig."""
    return ModelPolicyConfig()
