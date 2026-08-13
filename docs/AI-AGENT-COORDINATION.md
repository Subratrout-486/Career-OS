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
8. Notion/Application Writer — persists the review package and Ready-to-Apply application record.

## Provider policy

Generation providers may use the configured fallback chain (GitHub Models → Gemini → xAI → DeepSeek, subject to configuration and availability).

The independent Challenger is different: it is xAI/Grok-only. A challenger failure is surfaced explicitly rather than silently substituted with Gemini/GitHub/DeepSeek.

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

## Safety boundary

No agent may:
- fabricate career evidence
- promote Needs-Confirmation evidence to confirmed without user confirmation
- delete canonical Evidence Vault history
- submit an application
- expose secrets in logs or repository files

Code-changing agents must inspect → modify → test → report. Production changes should be small and reversible.

## Desired automated flow

Job capture → active verification → JD analysis → evidence retrieval → fit → resume → truth guard → ATS → independent Grok challenge → Notion review/application record → Ready to Apply → user review → user submission.
