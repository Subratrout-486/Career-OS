import asyncio, os, json
from dotenv import load_dotenv
from .agents import AgentRuntime
from .models import Job, PipelineResult
from .notion import NotionReviewQueue

load_dotenv()

class CareerOS:
    def __init__(self):
        self.runtime = AgentRuntime()
        self.notion = NotionReviewQueue()

    async def process(self, profile: str, job: Job) -> PipelineResult:
        fit = await self.runtime.fit(profile, job)
        if fit.recommendation == "SKIP":
            result = PipelineResult(job=job, fit=fit, review_status="SKIPPED")
            return result
        resume = await self.runtime.resume(profile, job, fit)
        # Hard safety gate: never put an unsupported resume into the review queue as approved.
        challenger = await self.runtime.challenge(profile, job, fit, resume)
        result = PipelineResult(job=job, fit=fit, resume=resume, challenger_notes=challenger, review_status="READY_FOR_REVIEW")
        await self.notion.create_review_page(result.model_dump())
        return result

def load_profile(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Career OS multi-agent pipeline")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--job-json", required=True, help="Path to a JSON file containing title/company/description and optional metadata")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    with open(args.job_json, "r", encoding="utf-8") as f:
        job = Job.model_validate(json.load(f))
    result = asyncio.run(CareerOS().process(profile, job))
    print(result.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
