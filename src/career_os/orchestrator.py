"""Career OS integrated pipeline orchestrator.

Flow:
  Job → active verification → JD analysis → live evidence vault → retrieve →
  fit → resume → deterministic truth guard → ATS → challenger → Notion review
  → Applications (Ready to Apply)

Production never silently falls back to the offline snapshot.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Sequence

from dotenv import load_dotenv

from .agents import AgentRuntime
from .ats_audit import audit_resume
from .evidence import EvidenceItem, retrieve_evidence
from .evidence_loader import VaultLoadError, load_evidence_vault
from .jd_analyzer import analyze_jd, requirements_for_retrieval
from .job_verify import verify_job_active
from .models import Job, JobVerificationModel, PipelineResult
from .notion import NotionReviewQueue
from .applications import ApplicationsTracker
from .resume_files import generate_resume_files
from .truth_guard import validate_resume_truth
