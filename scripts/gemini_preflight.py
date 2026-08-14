"""Safe Gemini configuration and reachability diagnostic for CI logs."""

from __future__ import annotations

import asyncio
import json

from career_os.agents import AgentRuntime


async def main() -> None:
    diagnostic = await AgentRuntime().gemini_preflight()
    print(json.dumps(diagnostic, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
