#!/usr/bin/env python3
"""Run the owner-controlled Career OS local model gateway.

Prerequisites on the worker machine:
  1. Ollama installed and running.
  2. A local model pulled (default: qwen2.5:7b).
  3. CAREER_OS_LOCAL_MODEL_TOKEN set to a long random bearer token.

The gateway is intentionally bound to 127.0.0.1 by default. Put it behind an
owner-controlled private tunnel/network only when remote Career OS execution
is required; never expose it publicly without authentication and network policy.
"""
from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "career_os.local_model_gateway:app",
        host=os.getenv("LOCAL_MODEL_GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("LOCAL_MODEL_GATEWAY_PORT", "8765")),
        reload=False,
    )
