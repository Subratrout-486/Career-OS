# Job Intake Provider Failure — 2026-08-17

## Incident
Career OS Job Intake run `32019948430` for Issue #78 failed during the primary fit stage.

## Root cause
The configured automatic primary-provider cascade had no usable provider:

- xAI `grok-4.6`: HTTP 403 — the xAI team has no credits/licenses for the model/chat endpoint.
- DeepSeek `deepseek-chat`: HTTP 402 — account balance/payment required.
- GitHub Models: HTTP 410 — the configured `models.github.ai/inference/chat/completions` endpoint is gone/unsupported.

Gemini preflight succeeded, proving the Gemini credential and configured model were reachable. However, the current automatic routing did not use Gemini as the primary fit fallback in this run.

## Secondary failure
Because the orchestrator raised before emitting valid `pipeline-result.json`, the Notion sync step then failed with `JSONDecodeError` while attempting to read the empty/invalid result file.

## Required engineering fix
1. Make automatic primary routing provider-aware at runtime, not merely credential-aware.
2. If xAI/DeepSeek/GitHub Models are unavailable, route the primary fit/resume stages to an eligible configured provider such as Gemini when policy permits.
3. Remove or disable known-dead GitHub Models endpoint configuration rather than repeatedly attempting it.
4. Persist a valid structured failure `pipeline-result.json` even when the AI cascade is exhausted, so Notion sync records the partial job and failure reason instead of failing secondarily.
5. Add regression tests for: xAI 403 -> DeepSeek 402 -> GitHub 410 -> Gemini success; all providers unavailable; malformed/empty pipeline result; and partial Notion job persistence.

Do not weaken Truth Guard, independent review, or application safety gates to make the provider cascade pass.
