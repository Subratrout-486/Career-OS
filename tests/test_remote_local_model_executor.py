from unittest.mock import AsyncMock, patch

import httpx
import pytest

from career_os.remote_model_executor import RemoteLocalModelExecutor


@pytest.mark.asyncio
async def test_remote_local_executor_requires_gateway_attestation():
    executor = RemoteLocalModelExecutor(base_url="http://worker", token="secret")
    response = httpx.Response(200, json={"text": "READY", "executor": "ollama", "model": "qwen2.5:7b", "fallback": False})
    response.request = httpx.Request("POST", "http://worker/generate")
    with patch("career_os.remote_model_executor.httpx.AsyncClient") as client_cls:
        client = client_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=response)
        result = await executor.generate(system="system", user="user")
    assert result == "READY"


@pytest.mark.asyncio
async def test_remote_local_executor_rejects_fallback_attestation():
    executor = RemoteLocalModelExecutor(base_url="http://worker", token="secret")
    response = httpx.Response(200, json={"text": "READY", "executor": "unknown", "model": "unknown", "fallback": True})
    response.request = httpx.Request("POST", "http://worker/generate")
    with patch("career_os.remote_model_executor.httpx.AsyncClient") as client_cls:
        client = client_cls.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=response)
        with pytest.raises(Exception, match="strict no-fallback"):
            await executor.generate(system="system", user="user")
