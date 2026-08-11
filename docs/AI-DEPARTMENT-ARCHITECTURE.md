# Career OS — AI Department Architecture

## Operating principle
Notion is the career command center and source of truth. External tools are specialized workers. The system must preserve human approval before a job is applied to and before an application is submitted.

## Departments

| Department | Primary | Role |
|---|---|---|
| Job Discovery | Scout + Jobright | Discover and rank live opportunities |
| LinkedIn Discovery | LinkedIn + compliant job signals | Surface relevant LinkedIn opportunities without unauthorized scraping/automation |
| JD & Career Intelligence | ChatGPT / Career OS | Fit, blockers, evidence mapping and apply/skip recommendation |
| Resume Tailoring | Claude | Produce a JD-specific resume from the approved Master Resume |
| ATS Audit | Jobscan (evaluate before purchase) | Identify ATS/keyword/format gaps; never invent claims |
| Application Autofill | Simplify | Fill repetitive application fields after approval |
| Application Tracking | Huntr + Notion | Secondary tracker + canonical application record in Notion |
| Company Research | Perplexity (evaluate) | Company, product, competitor and current-event research |
| Interview Preparation | Final Round AI (evaluate) + ChatGPT | Interview questions, technical preparation and answer practice |
| Communication Practice | Yoodli (evaluate) | Speaking and delivery practice |
| Independent Challenger | Grok | Second opinion and risk/challenge analysis |
| Career Strategy | ChatGPT / Career OS | Long-term targeting, prioritization and career decisions |
| Learning | ChatGPT + Coursera | Skill-gap diagnosis and structured learning |
| Technical Infrastructure | GitHub | Prompts, configuration, automation code, version history and portfolio assets |

## Per-job workflow

1. Discovery tool finds a live job.
2. Job enters the Notion review pipeline.
3. JD Intelligence analyzes the role against the verified Career Profile.
4. If worthwhile, Resume Tailoring creates a unique resume for that exact JD.
5. ATS Audit checks alignment.
6. User reviews the JD, fit analysis and tailored resume in Notion.
7. User approves or rejects.
8. Simplify assists with application autofill.
9. User reviews application answers.
10. User submits the application.
11. Notion records company, role, source, URL, date, resume version and status.
12. Interview workflow activates if shortlisted.

## Resume policy

- One Master Resume is the source of truth.
- Every serious application gets its own tailored resume derived from the Master Resume.
- Tailoring may change emphasis, ordering, wording and keyword alignment.
- Tailoring may not fabricate metrics, certifications, employers, degrees, tools, responsibilities or production experience.
- The user is the final approver of every tailored resume.

## Human approval gates

- Gate 1: Apply / Skip decision.
- Gate 2: Tailored resume approval.
- Gate 3: Application-answer approval.
- Gate 4: Final submission.

## LinkedIn rule

The Career OS may process compliant job alerts, feeds, user-provided job links or approved integrations. It must not use unauthorized scraping, browser automation or automatic Easy Apply submission. LinkedIn remains the destination where the user reviews and submits the application.

## Cost rule

Start with free tiers. Do not purchase premium auto-apply or redundant AI subscriptions until the end-to-end workflow has been tested and a specific paid feature is shown to materially improve output.
