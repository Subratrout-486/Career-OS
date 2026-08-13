# Wells Fargo Fit Remediation Report

## Result

The Wells Fargo `Technology Operations Analyst` job was rerun through the canonical Career OS pipeline after narrowing fit evidence retrieval. The fit request completed within the bounded provider timeout. No Notion records were written and no application was opened or submitted.

| Stage | Outcome |
|---|---|
| LinkedIn discovery | PASS — authenticated LinkedIn Jobs session used |
| Active verification | PASS — HTTP 200; title, company, location, and description checks passed |
| JD analysis | PASS — 10 compact retrieval requirements; the noisy full-paragraph responsibility blob was excluded from retrieval queries |
| Fit | PASS — score 68, recommendation REVIEW, band B |
| Evidence | PASS — 18 usable professional evidence items; Truth Guard attribution remained enforced |
| Resume | PASS — DOCX and PDF artifacts generated |
| ATS | PASS — score 100; 8 matched keywords and Azure explicitly unsupported/missing |
| Truth Guard | BLOCKED for application — unsupported or unconfirmed claims remain, including ITIL, Azure, Windows/AD/Exchange/Office365/Intune, VMware, Cisco/LAN/WAN, and Apple support |
| Salary | ADVISORY ONLY — no usable dated source observations; compensation remains human-controlled |
| Notion | NO-WRITE PILOT — no production page created or updated |
| Application page | NOT REACHED |
| Application Mode | DO_NOT_APPLY |
| Submission | 0 |

## Root cause and fix

The Wells Fargo JD parser produced a long full-sentence responsibility blob because the captured LinkedIn description did not expose structured section bullets. That blob was passed into evidence retrieval, where generic terms such as support, application, monitor, and technical support caused broad evidence matching and inflated the fit context.

The minimal fix filters retrieval-only requirements longer than 180 characters while retaining compact mandatory, preferred, technical, tool, domain, education, screening, keyword, and experience requirements. The fuller evidence pack remains available to downstream resume, ATS, Truth Guard, and review logic. No evidence acceptance, employer attribution, Truth Guard, or application-mode rule was relaxed.

## Measured effect

The Wells Fargo fit user payload decreased from 29,020 to 26,997 characters. Fit evidence decreased from 18 items / 12,790 characters to 15 items / 10,767 characters. The bounded Manus request timeout remains active; a timeout is still represented as not evaluated rather than as a fit result.

## Validation

The deterministic suite passed with 75 tests. Python compile checks and whitespace validation passed. The completed one-job result is stored in `pilot/one_job_result.json`. The run remained no-write and stopped before any application page or submission.

## Remaining blockers

The job is not eligible for automatic application. The fit result is `REVIEW`, and Truth Guard/application-mode safeguards classify it as `DO_NOT_APPLY` because unsupported or unconfirmed claims remain. XAI challenger credentials are not configured, so the independent challenger was not run. These are reported blockers, not silently bypassed.
