# Career OS — AI Agent Coordination Protocol

## Purpose

Career OS uses GitHub and Notion as shared state so agents do not require manual copy/paste handoffs.

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

1. JD Analyzer — decomposes the active JD into requirements.
2. Evidence Retrieval — searches the live Career Evidence Vault and preserves employer/status provenance.
3. Fit Agent — evaluates the JD against retrieved confirmed evidence.
4. Resume Agent — creates a truthful, JD-specific ATS resume using only vetted evidence.
5. Truth Guard — deterministic validation; blocks unsupported employer/tool/date claims.
6. ATS Auditor — measures transparent JD/resume coverage without inventing keywords.
7. Independent Challenger — xAI/Grok only. It must remain a genuinely separate provider and must never be replaced by the generation provider merely to make a run green.
8. Notion/Application Writer — persists the review package and application record.
9. Browser Executor / Manus — performs authenticated application execution only under the deterministic Application Mode safety contract.

## Provider policy

Generation providers may use the configured fallback chain, subject to configuration and availability.

The independent Challenger is different: it must remain a genuinely separate provider. A challenger failure is surfaced explicitly rather than silently substituted merely to make a run green.

## Failure handoff protocol

Every failure must include:
- job/run identifier
- pipeline stage
- exact error
- likely root cause
- relevant artifact/run URL
- safe next action

The automated failure workflow creates a structured GitHub issue for investigation. The issue is the shared handoff surface for external engineering agents such as Claude, Cursor, Manus, or Grok when they are being used interactively.

## External-agent boundary

Claude, Cursor, Manus, and the interactive Grok workspace are not assumed to expose a callable API from GitHub Actions. Therefore Career OS must never claim it can invoke those chat sessions automatically unless an explicit API/automation integration exists.

When such an integration is available, it should consume the same handoff issue and write results back to GitHub/Notion rather than introducing another private source of state.

## Delegated application authority

The user has explicitly authorized standing delegated submission authority. A second per-job confirmation is not required when deterministic Application Mode returns `AUTO_APPLY`.

`AUTO_APPLY` is allowed only when all existing safety conditions are verified: active/non-duplicate job, qualifying fit, Truth Guard pass, verified JD-specific resume, exact attachment verification, complete-form inspection, approved truthful answers for every required field, verified executable application path, and no CAPTCHA, OTP/MFA, identity/legal/sensitive question, compensation decision, assessment, unknown mandatory field, unsupported claim request, or other human-controlled gate.

Any failed condition produces `REVIEW_REQUIRED` with the exact blocker. The browser executor must never bypass a gate to obtain AUTO_APPLY. Submission is not considered complete until actual employer/LinkedIn confirmation is verified.

## Safety boundary

No agent may:
- fabricate career evidence
- promote Needs-Confirmation evidence to confirmed without user confirmation
- delete canonical Evidence Vault history
- submit an application unless Application Mode explicitly returns `AUTO_APPLY`
- treat resume upload as proof of submission
- expose secrets in logs or repository files

Code-changing agents must inspect → modify → test → report. Production changes should be small and reversible.

## Automated flow

Job capture → active verification → JD analysis → evidence retrieval → fit → resume → truth guard → ATS → independent challenge → Application Mode → browser execution → confirmation verification → Notion application tracking.

`REVIEW_REQUIRED` is an exception path, not a normal confirmation step. `AUTO_APPLY` is the standing delegated authorization to finish the application without another user prompt.
