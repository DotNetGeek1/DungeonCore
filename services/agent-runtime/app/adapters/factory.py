from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .azure_foundry import AzureAIFoundryAdapter, AzureAIFoundryConfig
from .base import ModelAdapter
from .lmstudio import LMStudioAdapter, LMStudioConfig

if TYPE_CHECKING:
    from shared_config.settings import ServiceSettings

logger = logging.getLogger(__name__)

PROVIDER_LMSTUDIO = "lmstudio"
PROVIDER_AZURE = "azure_ai_foundry"
PROVIDER_AZURE_ALT = "azure_foundry"

SUPPORTED_PROVIDERS = {PROVIDER_LMSTUDIO, PROVIDER_AZURE, PROVIDER_AZURE_ALT}


def create_adapter(settings: ServiceSettings) -> ModelAdapter:
    """Create the appropriate model adapter based on settings.

    The MODEL_PROVIDER environment variable determines which adapter is used:
    - "lmstudio" (default): Uses LM Studio's OpenAI-compatible API
    - "azure_ai_foundry": Uses Azure AI Foundry API

    Args:
        settings: Service settings containing provider configuration

    Returns:
        Configured ModelAdapter instance

    Raises:
        ValueError: If an unsupported provider is specified
    """
    provider = settings.model_provider.lower().strip()

    if provider not in SUPPORTED_PROVIDERS:
        logger.warning(
            f"Unknown provider '{provider}', falling back to '{PROVIDER_LMSTUDIO}'"
        )
        provider = PROVIDER_LMSTUDIO

    if provider in (PROVIDER_AZURE, PROVIDER_AZURE_ALT):
        return _create_azure_adapter(settings)

    return _create_lmstudio_adapter(settings)


def _create_lmstudio_adapter(settings: ServiceSettings) -> LMStudioAdapter:
    """Create and configure an LM Studio adapter."""
    base_url = (
        str(settings.lmstudio_base_url).rstrip("/")
        if settings.lmstudio_base_url
        else "http://localhost:1234"
    )

    config = LMStudioConfig(base_url=base_url)
    logger.info(f"Creating LMStudioAdapter with base_url={base_url}")
    return LMStudioAdapter(config)


def _create_azure_adapter(settings: ServiceSettings) -> AzureAIFoundryAdapter:
    """Create and configure an Azure AI Foundry adapter."""
    endpoint = (
        str(settings.azure_ai_foundry_endpoint)
        if settings.azure_ai_foundry_endpoint
        else ""
    )
    api_key = settings.azure_ai_foundry_api_key or ""
    model = settings.azure_ai_foundry_model_name or "gpt-4"

    if not endpoint:
        logger.warning(
            "Azure AI Foundry endpoint not configured. "
            "Set AZURE_AI_FOUNDRY_ENDPOINT environment variable."
        )

    if not api_key:
        logger.warning(
            "Azure AI Foundry API key not configured. "
            "Set AZURE_AI_FOUNDRY_API_KEY environment variable."
        )

    config = AzureAIFoundryConfig(
        endpoint=endpoint,
        api_key=api_key,
        model=model,
    )
    print(f"[AdapterFactory] Creating AzureAIFoundryAdapter with endpoint={endpoint}, model={model}")
    logger.info(f"Creating AzureAIFoundryAdapter with endpoint={endpoint}, model={model}")
    return AzureAIFoundryAdapter(config)
