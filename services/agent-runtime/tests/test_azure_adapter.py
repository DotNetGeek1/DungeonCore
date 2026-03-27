from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.adapters.azure_foundry import AzureAIFoundryAdapter, AzureAIFoundryConfig
from app.adapters.base import ModelRequest


class TestAzureAIFoundryConfig:
    def test_default_values(self) -> None:
        config = AzureAIFoundryConfig()
        assert config.endpoint == "https://example.services.ai.azure.com"
        assert config.api_key == ""
        assert config.model == "gpt-4"
        assert config.timeout_seconds == 120.0
        assert config.api_version == "2024-02-15-preview"

    def test_custom_values(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://custom.azure.com",
            api_key="test-key",
            model="gpt-4-turbo",
            timeout_seconds=60.0,
            api_version="2024-01-01",
        )
        assert config.endpoint == "https://custom.azure.com"
        assert config.api_key == "test-key"
        assert config.model == "gpt-4-turbo"


class TestAzureAIFoundryAdapter:
    def test_provider_name(self) -> None:
        adapter = AzureAIFoundryAdapter()
        assert adapter.provider_name == "azure_ai_foundry"

    @pytest.mark.asyncio
    async def test_generate_missing_api_key(self) -> None:
        config = AzureAIFoundryConfig(api_key="")
        adapter = AzureAIFoundryAdapter(config)

        request = ModelRequest(
            system_prompt="You are a helpful assistant",
            user_prompt="Hello",
        )

        response = await adapter.generate(request)
        assert response.success is False
        assert "missing API key" in response.error

    @pytest.mark.asyncio
    async def test_generate_missing_endpoint(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://example.services.ai.azure.com",  # Default/invalid
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        request = ModelRequest(
            system_prompt="You are a helpful assistant",
            user_prompt="Hello",
        )

        response = await adapter.generate(request)
        assert response.success is False
        assert "missing or invalid endpoint" in response.error

    @pytest.mark.asyncio
    async def test_generate_timeout_error(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            request = ModelRequest(
                system_prompt="You are a helpful assistant",
                user_prompt="Hello",
            )

            response = await adapter.generate(request)
            assert response.success is False
            assert response.error == "Request timed out"

    @pytest.mark.asyncio
    async def test_generate_auth_error_401(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="invalid-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_post.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=mock_response,
            )

            request = ModelRequest(
                system_prompt="System",
                user_prompt="User",
            )

            response = await adapter.generate(request)
            assert response.success is False
            assert "Authentication failed" in response.error

    @pytest.mark.asyncio
    async def test_generate_forbidden_403(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_post.side_effect = httpx.HTTPStatusError(
                "403 Forbidden",
                request=MagicMock(),
                response=mock_response,
            )

            request = ModelRequest(
                system_prompt="System",
                user_prompt="User",
            )

            response = await adapter.generate(request)
            assert response.success is False
            assert "Authorization failed" in response.error

    @pytest.mark.asyncio
    async def test_generate_rate_limit_429(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Too Many Requests"
            mock_post.side_effect = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=mock_response,
            )

            request = ModelRequest(
                system_prompt="System",
                user_prompt="User",
            )

            response = await adapter.generate(request)
            assert response.success is False
            assert "Rate limit exceeded" in response.error

    @pytest.mark.asyncio
    async def test_generate_model_not_found_404(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
            model="nonexistent-model",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_post.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=mock_response,
            )

            request = ModelRequest(
                system_prompt="System",
                user_prompt="User",
            )

            response = await adapter.generate(request)
            assert response.success is False
            assert "not found" in response.error.lower()

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {"content": "Hello! How can I help?"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 50},
            }
            mock_post.return_value = mock_response

            request = ModelRequest(
                system_prompt="You are a helpful assistant",
                user_prompt="Hello",
            )

            response = await adapter.generate(request)
            assert response.success is True
            assert response.raw_text == "Hello! How can I help?"
            assert response.finish_reason == "stop"
            assert response.tokens_used == 50

    @pytest.mark.asyncio
    async def test_health_check_missing_key(self) -> None:
        config = AzureAIFoundryConfig(api_key="")
        adapter = AzureAIFoundryAdapter(config)

        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await adapter.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        config = AzureAIFoundryConfig(
            endpoint="https://valid.azure.com",
            api_key="test-key",
        )
        adapter = AzureAIFoundryAdapter(config)

        with patch.object(adapter._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            result = await adapter.health_check()
            assert result is False
