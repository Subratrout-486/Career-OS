# Career OS

**Personal AI Career Operating System — an AI automation, agent orchestration, and workflow-engineering portfolio project.**

Career OS turns a job search into a controlled, observable workflow rather than a collection of disconnected AI chats and spreadsheets.

## Runtime principle

**Career OS itself does not depend on paid LLM API keys.** GitHub Actions performs deterministic scheduling, discovery, validation and durable queueing. Conductor/AgentFlow is the designated AI orchestration/runtime boundary for specialist agents, browser/search/app delegation and multi-agent reasoning.

The project must never introduce an xAI/Grok, Gemini, DeepSeek, OpenAI, or other paid model API merely as a fallback when Conductor is unavailable. If Conductor is unavailable, the system records the handoff state and waits rather than silently changing architecture.

## Live workflow

`08:00 / 20:00 IST → Company Discovery → Deduplicate/Validate → Trusted GitHub Intake → Conductor/AgentFlow → JD/Fit/Evidence → JD-specific Resume → Truth Guard → ATS/Review → Notion → Gated Browser Execution → Verification`

## Current architecture

- **Browser/control plane:** `src/career_os/api.py` exposes durable objectives, tasks, approvals, memory, audit events, usage, agents, models, and routing.
- **Durable platform state:** `src/career_os/control_plane.py` stores typed task, agent, model, message, approval, memory, audit and usage records atomically.
- **Career Evidence Vault:** Notion remains the production source of truth for confirmed career facts.
- **JD/Fit + Resume + Review:** executed through the Conductor agent runtime; deterministic Career OS code remains the safety/evidence layer.
- **Job Capture:** Chrome extension → GitHub issue intake, public employer ATS discovery, and Gmail job-alert intake.
- **Review Queue:** Notion API.
- **Application:** Career OS Application Mode determines `AUTO_APPLY`, `REVIEW_REQUIRED`, or `DO_NOT_APPLY`. An authenticated browser executor follows the verified application path only after all gates pass.
- **Tracking:** Notion + configured secondary trackers.

Discovery tools remain sources/inputs; Career OS does not bypass their access controls.

## Twice-daily company search

The company watchlist contains the Hyderabad MNC list. The deterministic discovery worker runs at **08:00 and 20:00 Asia/Kolkata** and searches configured official career/ATS sources. Unconfigured companies are reported as unconfigured rather than guessed.

For broader browser-based company-site discovery, the trusted GitHub intake is handed to Conductor. Conductor can assign specialist job-research agents to the remaining company sites without requiring a paid model API in GitHub Actions.

## AI agent system

The specialist roles include Job Research, JD Analyzer, Evidence Retrieval, Fit, Resume, Truth Guard, ATS, independent review, Notion/Application Writer and Browser Executor. Conductor coordinates the AI-capable roles; deterministic Career OS code enforces provenance, truthfulness, application safety and auditability.

See `CONDUCTOR_ARCHITECTURE.md` and `docs/AI-AGENT-COORDINATION.md` for the protocol.

## Resume safety

Only confirmed evidence can become professional resume content. Missing from the resume means **unknown**, not **no**. A JD keyword cannot create a responsibility. The Career Evidence Vault records employer, role, period, usage, context and safe/unsafe wording so confirmed facts can be reused across future tailored resumes without repeating the same questions.

## Truthfulness rules

- No fabricated metrics.
- No invented certifications.
- No invented employers, dates, titles, degree, tools, responsibilities or production experience.
- Learning/lab exposure must not be silently converted into professional experience.
- If evidence is missing, flag it as a gap and ask the user when the requirement matters.
- A high ATS score never overrides factual accuracy.
