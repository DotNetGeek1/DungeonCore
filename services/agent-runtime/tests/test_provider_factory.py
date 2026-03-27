from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.adapters.factory import (
    PROVIDER_AZURE,
    PROVIDER_LMSTUDIO,
    SUPPORTED_PROVIDERS,
    create_adapter,
    _create_azure_adapter,
    _create_lmstudio_adapter,
)
from app.adapters.lmstudio import LMStudioAdapter
from app.adapters.azure_foundry import AzureAIFoundryAdapter


class MockSettings:
    """Mock settings for testing."""

    def __init__(
        self,
        model_provider: str = "lmstudio",
        lmstudio_base_url: str | None = None,
        azure_ai_foundry_endpoint: str | None = None,
        azure_ai_foundry_api_key: str | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.lmstudio_base_url = lmstudio_base_url
        self.azure_ai_foundry_endpoint = azure_ai_foundry_endpoint
        self.azure_ai_foundry_api_key = azure_ai_foundry_api_key


class TestSupportedProviders:
    def test_lmstudio_in_supported(self) -> None:
        assert PROVIDER_LMSTUDIO in SUPPORTED_PROVIDERS

    def test_azure_in_supported(self) -> None:
        assert PROVIDER_AZURE in SUPPORTED_PROVIDERS

    def test_provider_constants(self) -> None:
        assert PROVIDER_LMSTUDIO == "lmstudio"
        assert PROVIDER_AZURE == "azure_ai_foundry"


class TestCreateAdapter:
    def test_default_to_lmstudio(self) -> None:
        settings = MockSettings(model_provider="lmstudio")
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, LMStudioAdapter)

    def test_azure_provider(self) -> None:
        settings = MockSettings(
            model_provider="azure_ai_foundry",
            azure_ai_foundry_endpoint="https://test.azure.com",
            azure_ai_foundry_api_key="test-key",
        )
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, AzureAIFoundryAdapter)

    def test_case_insensitive_provider(self) -> None:
        settings = MockSettings(model_provider="LMSTUDIO")
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, LMStudioAdapter)

    def test_provider_with_whitespace(self) -> None:
        settings = MockSettings(model_provider="  lmstudio  ")
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, LMStudioAdapter)

    def test_unknown_provider_falls_back_to_lmstudio(self) -> None:
        settings = MockSettings(model_provider="unknown_provider")
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, LMStudioAdapter)

    def test_empty_provider_falls_back_to_lmstudio(self) -> None:
        settings = MockSettings(model_provider="")
        adapter = create_adapter(settings)  # type: ignore
        assert isinstance(adapter, LMStudioAdapter)


class TestCreateLMStudioAdapter:
    def test_default_base_url(self) -> None:
        settings = MockSettings(lmstudio_base_url=None)
        adapter = _create_lmstudio_adapter(settings)  # type: ignore
        assert adapter.config.base_url == "http://localhost:1234"

    def test_custom_base_url(self) -> None:
        settings = MockSettings(lmstudio_base_url="http://custom:5678")
        adapter = _create_lmstudio_adapter(settings)  # type: ignore
        assert adapter.config.base_url == "http://custom:5678"


class TestCreateAzureAdapter:
    def test_with_credentials(self) -> None:
        settings = MockSettings(
            azure_ai_foundry_endpoint="https://myresource.azure.com",
            azure_ai_foundry_api_key="my-api-key",
        )
        adapter = _create_azure_adapter(settings)  # type: ignore
        assert adapter.config.endpoint == "https://myresource.azure.com"
        assert adapter.config.api_key == "my-api-key"

    def test_missing_endpoint(self) -> None:
        settings = MockSettings(
            azure_ai_foundry_endpoint=None,
            azure_ai_foundry_api_key="my-api-key",
        )
        adapter = _create_azure_adapter(settings)  # type: ignore
        assert adapter.config.endpoint == ""

    def test_missing_api_key(self) -> None:
        settings = MockSettings(
            azure_ai_foundry_endpoint="https://test.azure.com",
            azure_ai_foundry_api_key=None,
        )
        adapter = _create_azure_adapter(settings)  # type: ignore
        assert adapter.config.api_key == ""


class TestAdapterProviderName:
    def test_lmstudio_provider_name(self) -> None:
        settings = MockSettings(model_provider="lmstudio")
        adapter = create_adapter(settings)  # type: ignore
        assert adapter.provider_name == "lmstudio"

    def test_azure_provider_name(self) -> None:
        settings = MockSettings(model_provider="azure_ai_foundry")
        adapter = create_adapter(settings)  # type: ignore
        assert adapter.provider_name == "azure_ai_foundry"
