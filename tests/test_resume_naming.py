from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.resume_files import generate_resume_files


def test_subrat_rout_filename(tmp_path):
    job = {"company": "HighRadius", "title": "Product Support Engineer"}
    resume = {
        "title": "Product Support Engineer",
        "summary": "Support engineer.",
        "skills": ["ServiceNow", "SQL"],
        "experience": [{"title": "PSE", "company": "FactSet", "dates": "2024-2026", "bullets": ["L2 support"]}],
        "education": ["B.Com"],
    }
    paths = generate_resume_files(job, resume, output_dir=str(tmp_path))
    assert paths["pdf"].endswith("Subrat_Rout_HighRadius_Product-Support-Engineer_Resume.pdf")
    assert paths["docx"].endswith("Subrat_Rout_HighRadius_Product-Support-Engineer_Resume.docx")
    assert Path(paths["pdf"]).exists() and Path(paths["docx"]).exists()
    assert Path(paths["pdf"]).stat().st_size > 100
    assert Path(paths["docx"]).stat().st_size > 100


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_subrat_rout_filename(Path(d))
    print("PASS resume naming")
