"""Run provider availability checks inside the Conductor runtime only."""

from __future__ import annotations

import asyncio
import json

from career_os.agents import AgentRuntime


async def main() -> None:
    runtime = AgentRuntime()
    results = await runtime.preflight_providers()
    print(json.dumps(results, sort_keys=True))
    if not any(item.get("available") is True for item in results):
        raise SystemExit("NO_VERIFIED_PROVIDER_AVAILABLE")


if __name__ == "__main__":
    asyncio.run(main())

