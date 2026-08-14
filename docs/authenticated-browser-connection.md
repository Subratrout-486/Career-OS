# Authenticated Browser Connection for Career OS

## Purpose and non-negotiable safety boundary

Career OS may inspect or submit an application only through a **user-authorized Manus Browser Operator / My Browser session**. Career OS never requests, accepts, stores, logs, extracts, serializes, or replays a LinkedIn password, MFA or OTP code, session cookie, browser authentication token, authorization header, local storage value, or browser profile. The browser session remains a platform-managed user-browser capability rather than a Career OS data source. [1] [2]

> **Fail-closed rule.** If the browser executor cannot establish that the current task is using an already-authorized browser session, or if a verified site requires fresh authentication, Career OS records `REVIEW_REQUIRED / BROWSER_CONNECTION_REQUIRED`. It does not attempt login, session repair, credential recovery, CAPTCHA handling, or submission.

A connected session permits only browser visibility and interaction. It does **not** waive Truth Guard, active-job verification, ATS/recruiter/Gemini/design review, deduplication, exact-resume evidence, approved-answer, CAPTCHA/OTP/MFA, assessment, identity, sensitive-question, suspicious-redirect, final-review, or independent-confirmation requirements.

## Supported Manus browser-session model

Browser Operator operates in the user’s local Chrome or Edge context and uses that browser’s existing local login state, active tabs, and network context. The user enables **My Browser**, installs or enables the Browser Operator extension, and explicitly authorizes control when Manus requests it. [1] [2] Career OS does not create or manage a separate browser profile.

| Question | Supported answer and Career OS treatment |
|---|---|
| **Where is the authenticated profile stored?** | The effective authentication state remains in the user’s own local browser context. Official materials do not document an on-disk Browser Operator profile path. Career OS therefore neither reads nor writes a profile location. [1] [2] |
| **Does it survive a Manus task ending?** | Manus does not document a task-end persistence guarantee for Browser Operator. Career OS assumes nothing and performs a fresh non-submitting authenticated-session check whenever the task or preflight needs browser access. |
| **Does it survive Manus logout, restart, browser restart, target-site logout, or site expiry?** | No Browser Operator guarantee is documented for those events. Career OS treats all of them as possible invalidation events and stops at `REVIEW_REQUIRED / BROWSER_CONNECTION_REQUIRED` if the current task cannot use an authenticated session. |
| **Does Career OS reuse the session?** | Where the supported API exposes exactly one already-authorized online My Browser client, Career OS confirms that client **in memory for the waiting task only**. The local browser profile remains the source of authentication; Career OS does not retain a client ID or attempt cross-task session replay. [3] [4] |
| **Is this Cloud Browser persistence?** | No. Cloud Browser is a separate product with separately documented cookie/local-storage behavior. Career OS does not export, inspect, or copy Cloud Browser state, and must not represent Cloud Browser retention as Browser Operator behavior. [5] |

## Supported connection and reconnect procedure

The user completes all identity and authentication actions in their own browser. Career OS receives only non-secret availability and blocker outcomes.

| Step | User-controlled action | Career OS behavior | Required safe evidence |
|---|---|---|---|
| 1. Enable My Browser | Enable **My Browser** in Manus settings or the connection card, then enable the supported browser extension. | Starts only the task’s ordinary browser request; it does not inspect credentials. | A Browser Operator client is available to the current Manus task. |
| 2. Authorize the browser | Approve the prompted connection to the intended user browser. If more than one browser is online, choose the intended one in the Manus UI. | When exactly one authorized client is available to a waiting task, submits the documented in-memory `task.confirmAction` selection. If none or more than one is available, it stops at `BROWSER_CONNECTION_REQUIRED` or `BROWSER_SELECTION_REQUIRED`. [3] [4] | The task resumes from the user-authorized browser context. |
| 3. Authenticate personally if needed | Sign in directly with normal LinkedIn or employer/ATS controls. Complete any normal provider authentication yourself. | Never asks for or enters passwords, codes, recovery details, cookies, or tokens. | A member-only or employer-session probe renders without login redirect. |
| 4. Retest browser provenance | Keep the browser session available and return to the task. | Performs a non-submitting session and verified-URL check before discovering, preflighting, uploading, or answering application forms. | The browser is not identified as Sandbox and the site remains authenticated. |
| 5. Resume lifecycle | Trigger only the existing automated issues → `workflow_run` lifecycle after the staging/default-branch boundary is resolved. | Uses the existing durable lifecycle; no resume, pipeline result, browser state, or task artifact is manually downloaded, staged, or dispatched. | All existing Career OS gates pass independently. |

If authentication has expired, a browser task returns a browser-connection or preflight blocker, for example `BROWSER_UNAVAILABLE`, `BROWSER_CONNECTION_REQUIRED`, `AUTHENTICATED_LINKEDIN_SESSION_UNAVAILABLE`, or the verified site’s login redirect. Career OS persists the canonical **non-secret** blocker reason only and holds the record at `REVIEW_REQUIRED`.

## Runtime data-separation contract

Career OS calls the supported browser availability and task-confirmation interfaces only after a task reports `needConnectMyBrowser`. A local-browser client identifier and task confirmation event identifier are transient control-plane values used only while confirming that one task. They are removed before any snapshot is saved.

| Permitted durable information | Explicitly prohibited in Career OS state, GitHub, Notion, manifests, artifacts, logs, and source files |
|---|---|
| Task ID and task URL; application ID; verified application URL; exact JD-tailored resume filename and SHA-256; non-secret status such as `AUTHORIZED_BROWSER_SELECTED`; canonical blocker; evidence of employer/ATS/LinkedIn submission confirmation | Passwords; OTP/MFA values; recovery answers; cookies; browser tokens; session IDs; authorization headers; local storage; client identifiers; browser profile identifiers or paths; raw provider diagnostic/error payloads |

The execution-state store also removes private browser and authentication-shaped fields defensively. This is a safeguard against accidental future callers; it is not a mechanism for accessing browser state.

## Manual revocation and stopping work

The user remains in control of Browser Operator access. To stop a currently active task, close its dedicated task tab or stop the task from the Manus interface. To revoke ongoing Browser Operator access, disable **My Browser** in Manus Settings → Connectors; the extension can also be disabled or uninstalled. Close sensitive tabs and separately log out from LinkedIn or the relevant employer/ATS in the user browser when appropriate. [2] [6]

Career OS has no code path to revoke, clear, export, or manipulate browser authentication. It responds to revocation by observing that no supported browser client is available and returning `REVIEW_REQUIRED / BROWSER_CONNECTION_REQUIRED`.

## Detection and lifecycle behavior

The following checks are deliberately non-submitting. A successful check proves only that a user-authorized session is available; it does not authorize an application.

| Check | Pass condition | Fail-closed result |
|---|---|---|
| Browser availability | Exactly one already-authorized My Browser client is available when the Manus task requests connection. | `REVIEW_REQUIRED: BROWSER_CONNECTION_REQUIRED`, `BROWSER_SELECTION_REQUIRED`, or a specific connection blocker. |
| LinkedIn member session | A member-only LinkedIn URL renders without a redirect to `/login`. | `REVIEW_REQUIRED: AUTHENTICATED_LINKEDIN_SESSION_UNAVAILABLE`. |
| Direct ATS reachability | The verified application URL follows allowed redirects to the employer/ATS application route. | `REVIEW_REQUIRED: SUSPICIOUS_REDIRECT` or the applicable existing blocker. |
| Complete-form inspection | The page provides required-field and human-control observations without CAPTCHA, OTP/MFA, assessment, identity/consent, legal/sensitive, or unknown mandatory prompts. | `REVIEW_REQUIRED` with the exact observed blocker. |
| Submission reconciliation | The browser reports the exact tailored-resume proof and independent employer, ATS, or LinkedIn confirmation evidence. | `REVIEW_REQUIRED`; no `Applied` or durable `SUBMITTED` state is written. |

## Current live-test and deployment status

No application submission occurs as part of this browser-session infrastructure change. PR #35 remains **unmerged**. The previous controlled test correctly stopped when the executor was running in a Sandbox session and LinkedIn redirected a member-page request to sign-in.

An authenticated local browser session has subsequently been observed in this task, but the requested end-to-end test remains gated by a separate deployment boundary: the automatic `issues` → `workflow_run` definitions run from the repository default branch, whereas PR #35 remains unmerged. Career OS must not bypass that lifecycle by direct or manually staged execution. A live application test can resume only after an authorized staging/default-branch deployment path exists and the session checks above pass.

## References

[1] [Manus Browser Operator documentation](https://manus.im/docs/integrations/manus-browser-operator)

[2] [Manus Browser Operator feature documentation](https://manus.im/docs/features/browser-operator)

[3] [Manus task lifecycle — browser connection actions](https://open.manus.ai/docs/v2/task-lifecycle)

[4] [Manus `task.confirmAction` API documentation](https://open.manus.ai/docs/v2/task.confirmAction)

[5] [Manus Cloud Browser documentation](https://manus.im/docs/features/cloud-browser)

[6] [Manus Browser Operator connector guide](https://manus.im/blog/deep-dive-browser-operator-connector)
