# Authenticated Browser Connection for Career OS

## Purpose and safety boundary

Career OS can inspect and submit a browser application only through an authenticated user browser session that is explicitly connected to the current task. The application pipeline does not receive, request, store, or replay account passwords, one-time passwords, MFA codes, cookies, or session tokens. A connected session grants browser visibility and interaction only; it does not waive any Career OS verification gate.

> **Fail-closed rule.** If the browser executor cannot prove that it is operating in the user-connected authenticated session, the record is `REVIEW_REQUIRED` with `BROWSER_CONNECTION_REQUIRED / AUTHENTICATED_<SOURCE>_SESSION_UNAVAILABLE`. It must not search, upload a resume, answer questions, dispatch an execution task, or submit an application.

## Supported connection procedure

| Step | User action | Executor behavior | Evidence required before testing |
|---|---|---|---|
| 1. Enable task access | Enable the **My Browser** connector for this task. This enables use of the user browser; it does not expose credentials. | Starts an ordinary navigation required by the pending workflow. | The connector is enabled for the current task. |
| 2. Approve browser linking | When the task presents its browser-connection card after the first browser request, approve linking to the intended user browser session. | Waits for the linked session; it does not attempt to authenticate through a sandbox browser. | Browser actions identify the connected user session rather than `Sandbox`. |
| 3. Authenticate personally | In the linked browser, sign in to LinkedIn or the employer/ATS directly using normal provider controls. Complete any normal account authentication yourself. | Never asks for, inputs, stores, or transmits your password, MFA/OTP code, or recovery information. | A member-only, non-destructive URL renders without a sign-in redirect. |
| 4. Verify session binding | Leave the authenticated tab/session available and return to this task. | Performs a non-submitting member-page check before considering an application candidate. | The check returns authenticated page content and no `BROWSER_CONNECTION_REQUIRED` blocker. |
| 5. Begin controlled lifecycle | Authorize the application test only after the session check passes. | Begins normal discovery and uses the automated durable lifecycle; no files are downloaded, staged, or dispatched manually. | The qualifying job, application URL, exact tailored resume, and every Career OS gate pass. |

## What Career OS does not support

Career OS does not bypass LinkedIn or employer authentication, CAPTCHA, OTP/MFA, assessments, consent screens, identity checks, legal attestations, sensitive questions, or unknown mandatory questions. It does not use browser automation to create or recover an account, import cookies, scrape credentials, evade access controls, or convert a browser-session blocker into an automatic application attempt.

The normal browser executor also does not assume that a non-Easy-Apply role belongs to LinkedIn. Once a job is qualified, it follows the verified application URL and treats the destination as a direct employer/ATS flow only after the existing redirect, domain, and form-inspection safeguards have accepted it.

## Connection validation checks

The following checks are intentionally non-submitting. A pass confirms only that a browser session is available; it does not authorize an application.

| Check | Pass condition | Fail-closed result |
|---|---|---|
| LinkedIn member session | A member-only LinkedIn URL displays authenticated content without redirecting to `/login`. | `REVIEW_REQUIRED: AUTHENTICATED_LINKEDIN_SESSION_UNAVAILABLE` |
| Browser provenance | The executor is attached to the connected user browser, not a sandbox session. | `REVIEW_REQUIRED: BROWSER_CONNECTION_REQUIRED` |
| Direct ATS reachability | The verified application URL resolves through allowed redirects to an employer/ATS destination. | `REVIEW_REQUIRED: SUSPICIOUS_REDIRECT` or the applicable existing blocker |
| Human-control surfaces | No CAPTCHA, OTP/MFA, assessment, identity/consent, sensitive/legal, or unknown mandatory prompt is encountered. | `REVIEW_REQUIRED` with the exact observed blocker |

## Current controlled-test status

On 2026-08-14, the LinkedIn member-page check redirected to LinkedIn sign-in while the executor identified the current environment as `Sandbox`. Career OS correctly recorded `BROWSER_CONNECTION_REQUIRED / AUTHENTICATED_LINKEDIN_SESSION_UNAVAILABLE` and stopped before discovery, resume generation, preflight, upload, answer selection, dispatch, or submission. The direct employer/ATS test did not start because the test protocol requires an immediate stop on this browser-connection blocker.

A controlled two-channel rerun may begin only after the session-binding checks above pass. The rerun must retain the full chain—discovery, qualification, exact JD-tailored resume, Truth Guard, ATS/recruiter/Gemini/design gates, automatic lifecycle, preflight form inspection, exact-resume evidence, approved answers, final review, submission, independent confirmation, durable `SUBMITTED` status—and must stop at `REVIEW_REQUIRED` if any blocker appears.
