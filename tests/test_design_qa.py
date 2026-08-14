from pathlib import Path

from docx import Document
from fpdf import FPDF

from career_os.design_qa import audit_resume_design


def _make_resume_files(tmp_path: Path) -> dict[str, str]:
    pdf_path = tmp_path / "resume.pdf"
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for heading in ("PROFESSIONAL SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION"):
        pdf.multi_cell(0, 6, heading + "\nEvidence-grounded career content.")
    pdf.output(str(pdf_path))

    docx_path = tmp_path / "resume.docx"
    document = Document()
    for heading in ("PROFESSIONAL SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION"):
        document.add_paragraph(heading)
        document.add_paragraph("Evidence-grounded career content.")
    document.save(str(docx_path))
    return {"pdf": str(pdf_path), "docx": str(docx_path)}


def test_design_qa_accepts_clean_single_page_artifacts(tmp_path):
    result = audit_resume_design(_make_resume_files(tmp_path))
    assert result["passed"] is True
    assert result["metrics"]["pdf_pages"] == 1
    assert result["metrics"]["docx_tables"] == 0


def test_design_qa_fails_closed_when_artifacts_are_missing():
    result = audit_resume_design({})
    assert result["passed"] is False
    assert "final PDF is missing" in result["issues"]
    assert "final DOCX is missing" in result["issues"]
