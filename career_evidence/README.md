# Career Evidence Vault

This folder is the durable repository-side evidence layer for Career OS.

## Source hierarchy

1. `config/master_profile.md` — canonical resume baseline. The uploaded `Subrat_Rout_Resume_AWS_SEIII.pdf` wins over older records.
2. Career Evidence Vault — explicit user-confirmed facts that may not appear in the current resume.
3. JD requirements — requests for evidence, never evidence themselves.

## Core rule

**Absence from the resume is not evidence that the user did not do something.**

When a JD requirement is not supported by the canonical resume or an existing confirmed evidence record, Career OS must ask the user before using it professionally.

The question sequence is:

1. Did you use/do this professionally? (Y/N/Unsure)
2. At which employer/role?
3. During what period?
4. How did you use/do it?
5. What was the business/technical context?
6. What actions did you personally perform?
7. What wording is safe to put on a resume?
8. What wording would be an overclaim?

A `NO` answer is remembered so the same requirement is not repeatedly asked. An `UNSURE` answer stays pending. A `YES` answer is not resume-ready until employer/context/depth are captured.

## Resume generation rule

Only confirmed evidence can become a responsibility bullet. The generated bullet must preserve the confirmed employer, role, period and context. A JD keyword can never create a new responsibility by itself.

## Current pending evidence

See `records.json`. Jira is intentionally not marked professionally confirmed yet because the employer association has not been explicitly captured in the current conversation.
