# Career OS — AI Agent Coordination Protocol

## Purpose

Career OS uses GitHub and Notion as shared state so agents do not require manual copy/paste handoffs.

## Runtime boundary — important

**Career OS does not require paid model-provider API keys.** GitHub Actions is the deterministic scheduler and durable queue. **Conductor/AgentFlow is the designated AI runtime/orchestrator** for agent reasoning, browser/search/app delegation and multi-agent coordination.

GitHub Actions must not call xAI/Grok, Gemini, DeepSeek, OpenAI API, or another paid LLM provider merely to complete a Career OS run. A missing Conductor connection must produce a clear `CONDUCTOR_NOT_CONNECTED`/`READY_FOR_CONDUCTOR` state rather than a provider-cascade failure.

## Shared-state rule

GitHub is the engineering/control-plane source:
- source code
- tests
- workflow state
- job JSON intake
- pipeline artifacts
- agent handoff issues

Notion is the career/application data source:
- Career Evidence Vault
- Jobs
- Resume Library
- review records
- Applications

The Career Evidence Vault remains authoritative for career facts. A previous resume, prompt, or agent output can never upgrade an evidence item from unconfirmed to confirmed.

## Runtime agent roles

1. Job Research / Career-site agents — search the configured company list and resolve official career sources.
2. JD Analyzer — decomposes the active JD into requirements.
3. Evidence Retrieval — searches the live Career Evidence Vault and preserves employer/status provenance.
4. Fit Agent — evaluates the JD against retrieved confirmed evidence.
5. Resume Agent — creates a truthful, JD-specific ATS resume using only vetted evidence.
6. Truth Guard — deterministic validation; blocks unsupported employer/tool/date claims.
7. ATS Auditor — transparent JD/resume coverage without inventing keywords.
8. Independent reviewer/challenger — an agent available through the configured Conductor environment; it is not a reason to introduce a paid xAI API dependency.
9. Notion/Application Writer — persists the review package and application record.
10. Browser Executor / Manus — performs authenticated application execution only under the deterministic Application Mode safety contract.

## Provider policy

There is **no provider fallback chain in GitHub Actions**. Conductor owns model/agent selection inside the connected agent environment. Career OS owns deterministic truth, evidence, state, safety and audit.

## Failure handoff protocol

Every failure must include:
- job/run identifier
- pipeline stage
- exact error
- likely root cause
- relevant artifact/run URL
- safe next action

The issue is the durable handoff surface for Conductor and other connected agents.

## External-agent boundary

Claude, ChatGPT, Manus, Grok, Gemini, etc. are not assumed to expose a callable API from GitHub Actions. Career OS therefore never pretends it can invoke a chat session automatically. Conductor is the explicit orchestration boundary: when connected, it consumes the GitHub intake and writes structured results back to GitHub/Notion.

## Delegated application authority

`AUTO_APPLY` is allowed only when all existing safety conditions are verified: active/non-duplicate job, qualifying fit, Truth Guard pass, verified JD-specific resume, exact attachment verification, complete-form inspection, approved truthful answers for every required field, verified executable application path, and no CAPTCHA, OTP/MFA, identity/legal/sensitive question, compensation decision, assessment, unknown mandatory field, unsupported claim request, or other human-controlled gate.

Any failed condition produces `REVIEW_REQUIRED` with the exact blocker. The browser executor must never bypass a gate to obtain AUTO_APPLY. Submission is not considered complete until actual employer/ATS confirmation is verified.

## Automated flow

`08:00 / 20:00 IST → deterministic company discovery → trusted GitHub intake issue → Conductor/AgentFlow → JD/evidence/fit/resume/review → Notion → gated browser execution`

If Conductor is disconnected, discovery continues where public sources are configured, but AI processing and browser delegation must wait for Conductor. No paid-model fallback is permitted.
