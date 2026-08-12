import os
import httpx


async def challenge_with_grok(prompt: str) -> str:
    """Run the independent red-team review with xAI's Responses API."""
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY is missing; the independent challenge agent cannot run safely.")

    model = os.getenv("GROK_MODEL") or "grok-4.5"
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are the independent Career OS red-team reviewer. "
                    "Challenge fit and resume decisions. Never invent facts. "
                    "Identify unsupported claims, hard blockers, weak evidence, "
                    "and reasons the candidate should skip or revise the application."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "store": False,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.x.ai/v1/responses", headers=headers, json=payload
        )
        response.raise_for_status()
        data = response.json()
        return data.get("output_text", "").strip()
