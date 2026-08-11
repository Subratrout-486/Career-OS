import os
import httpx

async def challenge_with_grok(prompt: str) -> str:
    key = os.getenv("XAI_API_KEY")
    if not key:
        return "Grok challenger not configured: XAI_API_KEY is missing."
    model = os.getenv("GROK_MODEL", "grok-4.20-reasoning")
    payload = {"model": model, "input": prompt}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://api.x.ai/v1/responses", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("output_text", "")
