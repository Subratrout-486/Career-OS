import json
import os
import httpx
from .models import Job, FitReport, TailoredResume
from .structured_output import StructuredOutputError, extract_first_json_object

# CONTENT_TOO_LONG_FOR_SINGLE_MESSAGE — will fix via multi-step
TRUTH_RULES = """placeholder restore"""
