# One-job Career OS validation

## Job source

The authenticated LinkedIn browser session opened `https://www.linkedin.com/feed/` without redirecting to login. LinkedIn Jobs search was available, and the selected posting was Wells Fargo — Technology Operations Analyst. The JD was read from the LinkedIn job-detail view. No application controls were used.

## Stage results

| Stage | Result |
|---|---|
| LinkedIn authentication | PASS |
| Job discovery | PASS |
| Active posting/JD read | PASS |
| Career OS input manifest | PASS |
| Fit | BLOCKED: Manus provider request timed out; no fit report was produced |
| Evidence | NOT RUN because fit did not complete |
| Truth Guard | NOT RUN because fit did not complete |
| Resume tailoring | NOT RUN in this final attempt; an earlier run exposed and fixed DOCX control-character sanitization |
| ATS | NOT RUN |
| Notion | NOT RUN for this job; no write occurred |
| Application page | NOT REACHED |
| READY_TO_APPLY | NOT REACHED |
| Submission | 0; no application submitted |

## Fixes validated

The resume generator now removes invalid XML control characters from DOCX and PDF text paths. The deterministic test suite remains green at 72 passed, and Python compilation checks pass. Manus HTTP calls now have a bounded request timeout controlled by `AI_REQUEST_TIMEOUT_SECONDS` (default 45 seconds), preventing indefinite provider hangs.

## Remaining blocker

The real one-job run fails at the first fit call with `RuntimeError: All configured AI providers failed. manus:` after the bounded Manus request timeout. The provider smoke path works for small requests, but this full fit prompt did not return within the configured window. No fit, Truth Guard, resume, ATS, Notion, or application-page success is claimed.
