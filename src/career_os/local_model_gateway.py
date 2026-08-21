"""Authenticated local model gateway for the Career OS harness.

DeepSeek-Harness principle: the model is a replaceable capability behind a
stable execution seam. This gateway lets the Career OS control plane reach an
Ollama model running on the owner's machine without introducing a paid cloud
provider. The gateway never chooses a fallback provider.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .local_model_executor import OllamaModelExecutor


class GenerateRequest(BaseModel):
    system: str = Field(default="", max_length=50000)
    user: str = Field(min_length=1, max_length=100000)
    json_mode: bool = False
    max_tokens: int = Field(default=4000, ge=1, le=16000)


def create_local_model_gateway() -> FastAPI:
    token = os.getenv("CAREER_OS_LOCAL_MODEL_TOKEN", "").strip()
    model = os.getenv("LOCAL_MODEL", "qwen2.5:7b")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    executor = OllamaModelExecutor(model=model, base_url=ollama_url)
    app = FastAPI(title="Career OS Local Model Gateway", version="1.0")

    def authorize(authorization: str | None) -> None:
        if not token:
            raise HTTPException(status_code=503, detail="CAREER_OS_LOCAL_MODEL_TOKEN is not configured")
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid local model gateway token")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ready", "executor": "ollama", "model": model, "fallback": False}

    @app.post("/generate")
    async def generate(request: GenerateRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(authorization)
        try:
            text = await executor.generate(
                system=request.system,
                user=request.user,
                json_mode=request.json_mode,
                max_tokens=request.max_tokens,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"local model execution failed: {type(exc).__name__}") from exc
        return {"text": text, "executor": "ollama", "model": model, "fallback": False}

    return app


app = create_local_model_gateway()
