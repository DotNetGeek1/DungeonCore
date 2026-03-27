from __future__ import annotations

from functools import cached_property

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QueueTopologySettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=False,
        populate_by_name=True,
    )

    domain_exchange: str = "dungeoncore.domain"
    jobs_exchange: str = "dungeoncore.jobs"
    orchestration_events_queue: str = "dungeoncore.orchestration.events"
    narration_jobs_queue: str = "dungeoncore.jobs.narration"
    memory_jobs_queue: str = "dungeoncore.jobs.memory"
    ui_broadcast_queue: str = "dungeoncore.jobs.ui-broadcast"
    orchestration_events_routing_key: str = "orchestration.event.*"
    narration_jobs_routing_key: str = "job.narration"
    memory_jobs_routing_key: str = "job.memory"
    ui_broadcast_routing_key: str = "job.ui-broadcast"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=False,
        populate_by_name=True,
    )

    service_name: str = Field(default="service", alias="SERVICE_NAME")
    port: int = Field(default=8000, alias="PORT")
    postgres_dsn: str = Field(
        default="postgresql://dungeoncore:dungeoncore@localhost:5432/dungeoncore",
        alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL")
    lmstudio_base_url: AnyUrl | None = Field(default=None, alias="LMSTUDIO_BASE_URL")
    azure_ai_foundry_endpoint: AnyUrl | None = Field(default=None, alias="AZURE_AI_FOUNDRY_ENDPOINT")
    azure_ai_foundry_api_key: str | None = Field(default=None, alias="AZURE_AI_FOUNDRY_API_KEY")
    azure_ai_foundry_model_name: str = Field(default="gpt-4", alias="AZURE_AI_FOUNDRY_MODEL_NAME")
    websocket_base_url: AnyUrl | None = Field(default=None, alias="WEBSOCKET_BASE_URL")
    model_provider: str = Field(default="lmstudio", alias="MODEL_PROVIDER")
    api_port: int = Field(default=8000, alias="API_PORT")
    orchestrator_port: int = Field(default=8001, alias="ORCHESTRATOR_PORT")
    agent_runtime_port: int = Field(default=8002, alias="AGENT_RUNTIME_PORT")
    game_engine_port: int = Field(default=8003, alias="GAME_ENGINE_PORT")
    communication_service_port: int = Field(default=8004, alias="COMMUNICATION_SERVICE_PORT")

    @cached_property
    def queue_topology(self) -> QueueTopologySettings:
        return QueueTopologySettings()


class ServiceSettings(AppSettings):
    @classmethod
    def for_service(cls, default_name: str, default_port: int) -> "ServiceSettings":
        return cls(service_name=default_name, port=default_port)
