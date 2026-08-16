import re
from pathlib import Path

TARGET = Path("src/career_os/orchestrator.py")
text = TARGET.read_text(encoding="utf-8")
pattern = r"independent_ats = audit_independent_ats\((.*?)\n            \)"
replacement = r"independent_ats = audit_independent_ats(\1\n            ).as_dict()"
new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count:
    TARGET.write_text(new_text, encoding="utf-8")
print(f"Independent ATS normalization patch: replaced {count} call(s)")
compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec")
print("orchestrator.py syntax check: PASS")
