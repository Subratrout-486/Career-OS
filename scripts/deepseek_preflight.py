"""Run the DeepSeek independent-challenger preflight."""

from __future__ import annotations

import asyncio
import json

from career_os.agents import AgentRuntime


async def main() -> None:
    diagnostic = await AgentRuntime().deepseek_preflight()
    print(json.dumps(diagnostic, sort_keys=True))
    if diagnostic.get("provider_call_succeeded") is not True:
        raise SystemExit("DEEPSEEK_CHALLENGER_PREFLIGHT_FAILED")


if __name__ == "__main__":
    asyncio.run(main())

