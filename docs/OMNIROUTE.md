# OmniRoute integration

Career OS can use OmniRoute as an optional OpenAI-compatible AI gateway, but OmniRoute is a separate service and must be reachable by the process running Career OS.

## Important deployment rule

A hosted GitHub Actions runner cannot reach an OmniRoute instance running on the user's personal computer at `127.0.0.1:20128`. For GitHub Actions automation, OmniRoute must be deployed at a network-reachable HTTPS address, or the existing direct provider path should remain enabled.

For local Cursor/desktop development, a local OmniRoute instance is appropriate.

## Configuration contract

- `AI_PROVIDER=omniroute`
- `OMNIROUTE_BASE_URL=https://<reachable-host>/v1`
- `OMNIROUTE_API_KEY=<endpoint key created in OmniRoute>`
- `OMNIROUTE_MODEL=auto` or a provider/model identifier exposed by OmniRoute

Do not commit the API key.

## Architecture

Career OS -> OmniRoute OpenAI-compatible `/v1/chat/completions` -> configured provider/combo -> model

Grok remains the independent challenger and must not be routed through the same primary model path.

## Rollout rule

Do not make OmniRoute the production default until a real request succeeds from the same environment that runs Career OS and the complete pipeline has been validated. Keep the current Gemini/GitHub Models path available as the safe fallback.
