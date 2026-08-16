from pathlib import Path

TARGET = Path("src/career_os/agents.py")
text = TARGET.read_text(encoding="utf-8")
old = 'exclude_providers={"gemini"}'
count = text.count(old)
if count:
    text = text.replace(old, "exclude_providers=set()")
    TARGET.write_text(text, encoding="utf-8")
print(f"Gemini primary fallback patch: replaced {count} exclusion(s)")
compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec")
print("agents.py syntax check: PASS")
