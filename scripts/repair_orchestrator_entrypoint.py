from pathlib import Path

TARGET = Path("src/career_os/orchestrator.py")

MAIN = '''
    import argparse
    parser = argparse.ArgumentParser(description="Career OS multi-agent pipeline")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--browser-context-json")
    parser.add_argument("--no-notion-write", action="store_true")
    parser.add_argument("--offline-vault", action="store_true")
    parser.add_argument("--result-output")
    parser.add_argument("--manifest-output")
    parser.add_argument("--existing-application-page-id")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    with open(args.job_json, "r", encoding="utf-8") as f:
        job = Job.model_validate(json.load(f))

    browser_context = None
    if args.browser_context_json:
        with open(args.browser_context_json, "r", encoding="utf-8") as f:
            browser_context = json.load(f)
        if not isinstance(browser_context, dict):
            raise SystemExit("--browser-context-json must contain a JSON object")

    vault = None
    if args.offline_vault:
        from .evidence_vault_snapshot import VAULT_SNAPSHOT
        vault = VAULT_SNAPSHOT

    result = asyncio.run(CareerOS(
        vault=vault,
        write_to_notion=not args.no_notion_write,
    ).process(
        profile,
        job,
        browser_context=browser_context,
        existing_application_page_id=args.existing_application_page_id,
    ))

    result_data = result.model_dump()
    if args.manifest_output:
        try:
            manifest = generate_browser_execution_manifest(
                result_data,
                browser_context=browser_context,
                output_path=args.manifest_output,
            )
            result_data["browser_execution_manifest"] = manifest["manifest_path"]
        except ManifestGenerationError as exc:
            result_data.setdefault("errors", []).append(str(exc))
            result_data["review_status"] = "MANIFEST_GENERATION_FAILED"

    if args.result_output:
        Path(args.result_output).write_text(
            json.dumps(result_data, indent=2) + chr(10),
            encoding="utf-8",
        )
    print(json.dumps(result_data, indent=2))


if __name__ == "__main__":
    main()
'''

text = TARGET.read_text(encoding="utf-8")
if "from pathlib import Path" not in text:
    text = text.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nfrom pathlib import Path\n", 1)
if text.rstrip().endswith("def main():"):
    text = text.rstrip() + "\n" + MAIN.lstrip("\n")

TARGET.write_text(text, encoding="utf-8")
compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec")
print("orchestrator.py syntax check: PASS")
