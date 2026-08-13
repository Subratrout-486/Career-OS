import json
from pathlib import Path
from career_os.agents import FIT_PROMPT, TRUTH_RULES
from career_os.jd_analyzer import analyze_jd, requirements_for_retrieval
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT
from career_os.orchestrator import collect_relevant_evidence
from career_os.models import Job

base = Path(__file__).resolve().parent
job_data = json.loads((base / "one_job.json").read_text())
job = Job.model_validate(job_data[0] if isinstance(job_data, list) else job_data)
profile = (base.parent / "config" / "master_profile.md").read_text()
vault = VAULT_SNAPSHOT
jd = analyze_jd(job)
requirements = requirements_for_retrieval(jd)
full_evidence = collect_relevant_evidence(requirements, vault)
fit_evidence = collect_relevant_evidence(requirements, vault, include_all_usable=False)
def build_user(items):
    return FIT_PROMPT.format(
        truth_rules=TRUTH_RULES,
        profile=profile,
        evidence_pack=json.dumps(items, default=str, separators=(",", ":")),
        jd_analysis=json.dumps(jd.model_dump() if hasattr(jd, "model_dump") else jd, separators=(",", ":")),
        job=job.model_dump_json(indent=None),
    )
full_user = build_user(full_evidence)
fit_user = build_user(fit_evidence)
for name, value in {
    "profile_chars": profile,
    "job_chars": job.model_dump_json(indent=None),
    "jd_analysis_chars": json.dumps(jd.model_dump(), separators=(",", ":")),
    "full_evidence_chars": json.dumps(full_evidence, default=str, separators=(",", ":")),
    "fit_evidence_chars": json.dumps(fit_evidence, default=str, separators=(",", ":")),
    "full_fit_user_chars": full_user,
    "fit_user_chars": fit_user,
}.items():
    print(f"{name}={len(value)}")
print(f"full_evidence_items={len(full_evidence)}")
print(f"fit_evidence_items={len(fit_evidence)}")
print(f"requirements={len(requirements)}")
print("requirement_list=" + json.dumps(requirements))
