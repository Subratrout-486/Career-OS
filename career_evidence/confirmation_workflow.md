# JD Requirement Confirmation Workflow

For every JD requirement not already supported by the canonical resume or a confirmed Career Evidence Vault record:

```text
JD requirement
   |
   +--> Canonical resume supports it? ---- YES --> use with canonical employer/context
   |
   NO
   |
   +--> Evidence Vault supports it? ------- YES --> use confirmed employer/context
   |
   NO
   |
   +--> Previously rejected? -------------- YES --> do not use; do not ask again
   |
   NO
   |
   +--> Ask user:
          1. Did you use/do it professionally? Y/N/Unsure
          2. Which employer and role?
          3. When?
          4. How did you use/do it?
          5. What was the business/technical context?
          6. What did you personally do?
          7. What is safe resume wording?
          8. What would be an overclaim?
   |
   +--> YES + complete context --> CONFIRMED --> store reusable evidence
   +--> NO ----------------------> REJECTED --> never use as professional evidence
   +--> UNSURE -------------------> PENDING --> ask again only when the requirement matters and no answer exists
```

## Tailoring

For a JD, Career OS should build a requirement matrix with one of:

- `CANONICAL_RESUME`
- `CONFIRMED_EVIDENCE`
- `UNCONFIRMED`
- `REJECTED`
- `SELF_DIRECTED`
- `KNOWLEDGE_ONLY`
- `INFERRED`

Only the first two can create professional responsibility bullets.

A responsibility bullet must map back to an employer-specific evidence record. If the evidence says Jira was used for escalation, the resume may say that only under the confirmed employer/role once that association is captured. The JD itself can never supply the missing action.

## ATS principle

The target is not maximum keyword stuffing. The target is **high relevance with an auditable evidence trail**:

`JD requirement -> evidence record -> employer/role -> resume bullet -> ATS keyword`

This makes the match both ATS-relevant and interview-defensible.
