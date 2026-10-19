# Career OS Finalization Plan

## Goal

Make Career OS a reliable application-grade career operating system with a single canonical job pipeline.

## Required flow

`Discovery -> Canonical Job Record -> JD Verification -> Profile Fit Audit -> Resume -> Truth Guard -> ATS -> Ready to Apply -> Browser Execution -> Submission Verification -> Application Tracking`

## Stability gates

- Current main branch validation must pass.
- Historical failed commits must not trigger repeated self-heal notifications.
- A transient AI/provider failure must never discard a discovered job.
- Every valid discovered job must reach the canonical Jobs store with an explicit verification state.
- Job records must be idempotent and deduplicated.
- Ready to Apply must remain a gated state and must never imply Applied.
- Applied requires authoritative submission evidence.
- Scheduled discovery must be observable and recoverable.

## Daily discovery contract

Career OS discovery must use the confirmed target-role rules: prioritize Hyderabad Product Support, Technical/Application Support, Product/Technical Operations, Business/Operations Analyst, Data/Research Analyst and related corporate roles, then India-wide remote/hybrid. Professional Python is confirmed experience. Unsupported AWS, certifications, metrics, degree credentials, employers, dates or responsibilities must never be invented.

The discovery result must preserve:

- company
- exact title
- location
- source
- job URL when available
- capture/verification timestamps
- fit score
- matched evidence
- must-have blockers
- trainable gaps
- degree requirements
- shift/work-model constraints
- APPLY/SKIP decision
- verification state
- resume/ATS/Truth Guard state

## Failure handling

Discovery and ingestion are separated from enrichment. If enrichment fails, persist the raw candidate as `NEEDS_VERIFICATION` rather than dropping it. Retries must be idempotent. Failure notifications should be emitted only for the current active main revision and only once per unresolved incident; superseded historical revisions must not generate new user notifications.

## Final product gates

1. Stable scheduled intake.
2. Reliable canonical job sync.
3. Full audit visible in Notion.
4. Ready-to-Apply queue.
5. Application execution safety gates.
6. Verified application outcome.
7. Dashboard health/observability.
8. Automated regression and integration validation.
9. Deployment-ready configuration with secrets outside source control.
