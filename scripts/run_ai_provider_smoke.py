#!/usr/bin/env python3
"""Provider-only smoke test for the Career OS AI boundary.

This deliberately does not use Conductor and does not run the career pipeline.
It verifies that the configured direct model provider can answer a tiny request.
A pinned provider is fail-closed: this script excludes every other provider.
"""
from __future__ import annotations

import asyncio

from career_os.agents import AgentRuntime


PROVIDERS = {"manus", "gemini", "xai", "deepseek", "anthropic", "github"}


async def main() -> int:
    runtime = AgentRuntime()
    configured = runtime.provider

    if configured == "auto":
        raise SystemExit(
            "AI_PROVIDER=auto is not accepted for this smoke test. Pin one direct provider "
            "(manus, gemini, xai, deepseek, or anthropic)."
        )

    excluded = PROVIDERS - {configured}
    try:
        response = await runtime._chat(
            "You are a connectivity checker. Return exactly READY.",
            "Reply READY.",
            json_mode=False,
            max_tokens=8,
            exclude_providers=excluded,
        )
    except Exception as exc:
        print(f"AI_PROVIDER_SMOKE_FAILED provider={configured} error={type(exc).__name__}")
        return 1

    if response.strip() != "READY":
        print(f"AI_PROVIDER_SMOKE_FAILED provider={configured} unexpected_response")
        return 1

    print(f"AI_PROVIDER_SMOKE_PASSED provider={runtime.last_provider_used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
