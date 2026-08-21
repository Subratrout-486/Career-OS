"""Runtime truth-policy reconciliation for Career OS.

The canonical resume and career_evidence/records.json are the source of truth.
This module removes stale prompt-level denylist assumptions until the legacy
literal in agents.py can be deleted in a dedicated cleanup. It runs before
specialist_routing imports the prompt constants, so every agent path receives
the same reconciled policy.
"""

from __future__ import annotations


def install_truth_policy() -> bool:
    from . import agents

    stale_rules = '''- IGT group-reservations/backend-operations evidence is confirmed. Previously disputed IGT technical claims such as Python, SQL,
  Power Query, Power BI, REST API testing, and UAT remain Needs-Confirmation/Unconfirmed unless the current evidence pack explicitly
  marks them confirmed. Do not promote them because an old resume or target JD mentions them.
- HARD IGT RESUME PROHIBITION: Until the user explicitly confirms a change to the source-of-truth policy, never place Python,
  SQL, Power Query, Power BI, REST API testing, UAT, or Excel under IGT Solutions in the summary, skills, or experience bullets,
  even if those terms appear in MASTER_PROFILE, a historical resume, or the target JD. Keep those IGT claims out of the resume and
  list them only as unsupported/confirmation items when relevant. Salesforce operational/work-management use may be used only when
  the approved evidence pack maps it to IGT; do not infer Salesforce administration or development.
- Excel/Advanced Excel is unconfirmed unless the current evidence pack contains employer-specific confirmed evidence; do not add it
  as professional experience or attribute it to IGT.
'''

    current_rules = '''- IGT group-reservations/backend-operations evidence is confirmed. Employer/tool status MUST be resolved from the
  current MASTER_PROFILE plus approved evidence pack. A current evidence record marked Professional-Confirmed/Confirmed-by-User or
  Confirmed-by-Document overrides stale denylist assumptions or historical resume exclusions.
- The current canonical resume explicitly confirms Python, SQL, Power Query, Power BI, REST API testing, and UAT under IGT Solutions.
  When the evidence pack supplies those records as confirmed, they may be used under IGT in Summary, Skills, or Experience where the
  JD makes them relevant, using only the safe wording supplied by the evidence. Do not inflate the scope beyond that wording.
- Microsoft Excel is professionally confirmed for IGT and FactSet in the current evidence pack. It may be used under the correct
  employer when relevant, but do not infer VBA/macros/Power Pivot/advanced financial modeling unless separately evidenced.
- Salesforce operational/work-management use may be used only when the approved evidence pack maps it to IGT; do not infer Salesforce
  administration or development.
'''

    if stale_rules in agents.TRUTH_RULES:
        agents.TRUTH_RULES = agents.TRUTH_RULES.replace(stale_rules, current_rules, 1)

    stale_fit = '- Excel/Advanced Excel is unconfirmed: surface as a gap/confirmation request, not a fabricated match, and do not auto-reject solely for Excel.'
    current_fit = '- Excel/Advanced Excel is confirmed only to the scope represented in the approved evidence pack; do not fabricate advanced Excel features.'
    if stale_fit in agents.FIT_PROMPT:
        agents.FIT_PROMPT = agents.FIT_PROMPT.replace(stale_fit, current_fit, 1)

    stale_resume = '''9. Do not put Excel/Advanced Excel on the resume as professional experience until employer-specific confirmation exists.
10. Years-of-experience mismatch may be surfaced as a risk but never fabricated around.
11. evidence_trace should briefly map important tailored claims to the relevant employer/source evidence.
12. Treat the HARD IGT RESUME PROHIBITION above as an output constraint, not a suggestion; if the target JD requests a denied IGT
    tool, omit it from IGT history and record it as unsupported rather than copying it into Skills or Summary.
'''
    current_resume = '''9. Use professionally confirmed Excel only at the employer(s) mapped in the approved evidence pack and only within the confirmed scope.
10. Years-of-experience mismatch may be surfaced as a risk but never fabricated around.
11. evidence_trace should briefly map important tailored claims to the relevant employer/source evidence.
12. Never apply a stale employer/tool denylist when the current canonical resume and approved evidence pack explicitly confirm the
    employer/tool association. The evidence pack is the controlling employer-mapping layer for tailored output.
'''
    if stale_resume in agents.RESUME_PROMPT:
        agents.RESUME_PROMPT = agents.RESUME_PROMPT.replace(stale_resume, current_resume, 1)

    stale_challenge = "tools appear under the correct employer's Experience section when relevant. Verify that UNCONFIRMED tools (including Excel)\nwere not added."
    current_challenge = "tools appear under the correct employer's Experience section when relevant. Verify that UNCONFIRMED tools were not added\nand that confirmed tools are used only within the safe wording/scope in the evidence pack."
    if stale_challenge in agents.CHALLENGE_PROMPT:
        agents.CHALLENGE_PROMPT = agents.CHALLENGE_PROMPT.replace(stale_challenge, current_challenge, 1)

    # Fail closed if a stale hard denylist is somehow still active at runtime.
    if "HARD IGT RESUME PROHIBITION" in agents.TRUTH_RULES:
        raise RuntimeError("Stale IGT truth-policy denylist remains active")
    if "Excel/Advanced Excel is unconfirmed" in agents.FIT_PROMPT:
        raise RuntimeError("Stale Excel fit rule remains active")

    agents.TRUTH_POLICY_RECONCILED = True
    return True
