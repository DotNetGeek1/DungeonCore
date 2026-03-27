from __future__ import annotations

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model_policy import (
    ModelPolicy,
    ModelPolicyConfig,
    ModelPolicyDefaults,
    get_model_policy_config,
)
from shared_schemas.enums import ActorRole


class TestModelPolicy:
    def test_default_values(self) -> None:
        policy = ModelPolicy()
        assert policy.provider == "lmstudio"
        assert policy.model_name == "local-model"
        assert policy.temperature == 0.4
        assert policy.max_tokens == 2048
        assert policy.timeout_seconds == 120.0

    def test_custom_values(self) -> None:
        policy = ModelPolicy(
            provider="azure_ai_foundry",
            model_name="gpt-4",
            temperature=0.7,
            max_tokens=4096,
            timeout_seconds=180.0,
        )
        assert policy.provider == "azure_ai_foundry"
        assert policy.model_name == "gpt-4"
        assert policy.temperature == 0.7
        assert policy.max_tokens == 4096
        assert policy.timeout_seconds == 180.0

    def test_with_overrides_temperature(self) -> None:
        policy = ModelPolicy(temperature=0.4)
        new_policy = policy.with_overrides(temperature=0.9)
        assert new_policy.temperature == 0.9
        assert policy.temperature == 0.4  # Original unchanged

    def test_with_overrides_max_tokens(self) -> None:
        policy = ModelPolicy(max_tokens=2048)
        new_policy = policy.with_overrides(max_tokens=1024)
        assert new_policy.max_tokens == 1024

    def test_with_overrides_timeout(self) -> None:
        policy = ModelPolicy(timeout_seconds=120.0)
        new_policy = policy.with_overrides(timeout_seconds=60.0)
        assert new_policy.timeout_seconds == 60.0

    def test_with_overrides_preserves_other_values(self) -> None:
        policy = ModelPolicy(
            provider="lmstudio",
            model_name="custom-model",
            temperature=0.5,
            max_tokens=3000,
        )
        new_policy = policy.with_overrides(temperature=0.8)
        assert new_policy.provider == "lmstudio"
        assert new_policy.model_name == "custom-model"
        assert new_policy.max_tokens == 3000

    def test_with_overrides_none_keeps_original(self) -> None:
        policy = ModelPolicy(temperature=0.5, max_tokens=2048)
        new_policy = policy.with_overrides(temperature=None, max_tokens=None)
        assert new_policy.temperature == 0.5
        assert new_policy.max_tokens == 2048


class TestModelPolicyDefaults:
    def test_dm_defaults(self) -> None:
        defaults = ModelPolicyDefaults()
        assert defaults.dm.temperature == 0.7
        assert defaults.dm.max_tokens == 4096

    def test_player_defaults(self) -> None:
        defaults = ModelPolicyDefaults()
        assert defaults.player.temperature == 0.4
        assert defaults.player.max_tokens == 2048

    def test_narrator_defaults(self) -> None:
        defaults = ModelPolicyDefaults()
        assert defaults.narrator.temperature == 0.5
        assert defaults.narrator.max_tokens == 1024

    def test_default_policy(self) -> None:
        defaults = ModelPolicyDefaults()
        assert defaults.default.temperature == 0.4
        assert defaults.default.max_tokens == 2048


class TestModelPolicyConfig:
    def test_get_policy_for_dm_role(self) -> None:
        config = ModelPolicyConfig()
        policy = config.get_policy_for_role(ActorRole.DM)
        assert policy.temperature == 0.7
        assert policy.max_tokens == 4096

    def test_get_policy_for_player_role(self) -> None:
        config = ModelPolicyConfig()
        policy = config.get_policy_for_role(ActorRole.PLAYER)
        assert policy.temperature == 0.4
        assert policy.max_tokens == 2048

    def test_get_policy_for_npc_role(self) -> None:
        config = ModelPolicyConfig()
        policy = config.get_policy_for_role(ActorRole.NPC)
        assert policy == config.defaults.default

    def test_agent_override(self) -> None:
        config = ModelPolicyConfig()
        custom_policy = ModelPolicy(temperature=0.9, max_tokens=1000)
        config.set_agent_override("agent-123", custom_policy)

        policy = config.get_policy_for_agent("agent-123")
        assert policy.temperature == 0.9
        assert policy.max_tokens == 1000

    def test_agent_fallback_to_role(self) -> None:
        config = ModelPolicyConfig()
        policy = config.get_policy_for_agent("unknown-agent", role=ActorRole.DM)
        assert policy.temperature == 0.7

    def test_agent_fallback_to_default(self) -> None:
        config = ModelPolicyConfig()
        policy = config.get_policy_for_agent("unknown-agent", role=None)
        assert policy == config.defaults.default

    def test_remove_agent_override(self) -> None:
        config = ModelPolicyConfig()
        custom_policy = ModelPolicy(temperature=0.9)
        config.set_agent_override("agent-123", custom_policy)

        assert config.remove_agent_override("agent-123") is True
        policy = config.get_policy_for_agent("agent-123", role=ActorRole.PLAYER)
        assert policy.temperature == 0.4  # Falls back to player default

    def test_remove_nonexistent_override(self) -> None:
        config = ModelPolicyConfig()
        assert config.remove_agent_override("nonexistent") is False

    def test_list_agent_overrides(self) -> None:
        config = ModelPolicyConfig()
        config.set_agent_override("agent-1", ModelPolicy())
        config.set_agent_override("agent-2", ModelPolicy())

        overrides = config.list_agent_overrides()
        assert "agent-1" in overrides
        assert "agent-2" in overrides
        assert len(overrides) == 2


class TestModelPolicyConfigFromSettings:
    def test_from_settings_basic(self) -> None:
        config = ModelPolicyConfig.from_settings(
            provider="lmstudio",
            default_model="my-model",
        )
        assert config.defaults.default.provider == "lmstudio"
        assert config.defaults.default.model_name == "my-model"

    def test_from_settings_dm_model(self) -> None:
        config = ModelPolicyConfig.from_settings(
            dm_model="gpt-4-turbo",
            dm_temperature=0.8,
        )
        assert config.defaults.dm.model_name == "gpt-4-turbo"
        assert config.defaults.dm.temperature == 0.8

    def test_from_settings_player_model(self) -> None:
        config = ModelPolicyConfig.from_settings(
            player_model="gpt-3.5-turbo",
            player_temperature=0.3,
        )
        assert config.defaults.player.model_name == "gpt-3.5-turbo"
        assert config.defaults.player.temperature == 0.3

    def test_from_settings_narrator_model(self) -> None:
        config = ModelPolicyConfig.from_settings(
            narrator_model="gpt-4",
            narrator_temperature=0.6,
        )
        assert config.defaults.narrator.model_name == "gpt-4"
        assert config.defaults.narrator.temperature == 0.6

    def test_from_settings_timeout(self) -> None:
        config = ModelPolicyConfig.from_settings(default_timeout=180.0)
        assert config.defaults.default.timeout_seconds == 180.0
        assert config.defaults.dm.timeout_seconds == 180.0
        assert config.defaults.player.timeout_seconds == 180.0

    def test_from_settings_fallback_model_name(self) -> None:
        config = ModelPolicyConfig.from_settings(
            default_model="fallback-model",
            dm_model=None,
            player_model=None,
        )
        assert config.defaults.dm.model_name == "fallback-model"
        assert config.defaults.player.model_name == "fallback-model"


class TestGetModelPolicyConfig:
    def test_factory_returns_config(self) -> None:
        config = get_model_policy_config()
        assert isinstance(config, ModelPolicyConfig)
        assert config.defaults is not None
