from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPolicySettings(BaseSettings):
    """Environment-driven model policy configuration.

    These settings define default models and parameters for different agent roles.
    All values can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=False,
        populate_by_name=True,
    )

    default_model_name: str = Field(
        default="local-model",
        alias="DEFAULT_MODEL_NAME",
        description="Default model name for all agents",
    )
    default_temperature: float = Field(
        default=0.4,
        alias="DEFAULT_TEMPERATURE",
        description="Default temperature for model generation",
    )
    default_max_tokens: int = Field(
        default=2048,
        alias="DEFAULT_MAX_TOKENS",
        description="Default maximum tokens for model generation",
    )
    default_timeout_seconds: float = Field(
        default=120.0,
        alias="DEFAULT_TIMEOUT_SECONDS",
        description="Default timeout for model API calls",
    )

    dm_model_name: str | None = Field(
        default=None,
        alias="DM_MODEL_NAME",
        description="Model name for DM agents (falls back to default)",
    )
    dm_temperature: float = Field(
        default=0.7,
        alias="DM_TEMPERATURE",
        description="Temperature for DM agents (higher for creativity)",
    )
    dm_max_tokens: int = Field(
        default=4096,
        alias="DM_MAX_TOKENS",
        description="Max tokens for DM agents (higher for narration)",
    )

    player_model_name: str | None = Field(
        default=None,
        alias="PLAYER_MODEL_NAME",
        description="Model name for player agents (falls back to default)",
    )
    player_temperature: float = Field(
        default=0.4,
        alias="PLAYER_TEMPERATURE",
        description="Temperature for player agents",
    )
    player_max_tokens: int = Field(
        default=2048,
        alias="PLAYER_MAX_TOKENS",
        description="Max tokens for player agents",
    )

    narrator_model_name: str | None = Field(
        default=None,
        alias="NARRATOR_MODEL_NAME",
        description="Model name for narrator agents (falls back to default)",
    )
    narrator_temperature: float = Field(
        default=0.5,
        alias="NARRATOR_TEMPERATURE",
        description="Temperature for narrator agents",
    )
    narrator_max_tokens: int = Field(
        default=1024,
        alias="NARRATOR_MAX_TOKENS",
        description="Max tokens for narrator agents",
    )


def get_model_policy_settings() -> ModelPolicySettings:
    """Load model policy settings from environment."""
    return ModelPolicySettings()
