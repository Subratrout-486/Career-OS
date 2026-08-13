"""Recalculate one Notion Application status after human edits.

This script only reads Application Questions and updates the matching Application's
status/next action. It never writes answers and never submits an application.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from career_os.application_questions import ApplicationQuestionStore
from career_os.applications import ApplicationsTracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-id", required=True, help="Notion Application page ID")
    parser.add_argument(
        "--resume-review-approved",
        action="store_true",
        help="Set only after the user has reviewed and approved the tailored resume",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    store = ApplicationQuestionStore()
    readiness = await store.readiness(args.application_id)
    status = await ApplicationsTracker().update_readiness(
        args.application_id,
        questions_ready=bool(readiness.get("ready")),
        resume_review_approved=args.resume_review_approved,
    )
    print({"application_id": args.application_id, "status": status, "readiness": readiness})


if __name__ == "__main__":
    asyncio.run(main())
