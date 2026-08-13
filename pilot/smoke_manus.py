import asyncio

from career_os.agents import AgentRuntime


async def main():
    runtime = AgentRuntime()
    response = await runtime._chat(
        "Return concise JSON only.",
        'Return exactly {"status":"ok"}.',
        json_mode=True,
        max_tokens=100,
    )
    print(f"provider={runtime.last_provider_used}")
    print(f"response={response}")


if __name__ == "__main__":
    asyncio.run(main())
