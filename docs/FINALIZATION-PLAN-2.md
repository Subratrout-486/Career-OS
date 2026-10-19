# Finalization implementation

The next implementation work must modify existing workflows and pipeline code, not create parallel job stores. The canonical Jobs database remains the system of record.

Required invariants:

- Persist discovery before enrichment.
- Never drop a candidate because an AI/provider stage fails.
- Deduplicate by stable source/job identity before writing.
- Sync both successful and partial results to the canonical job store.
- Persist the complete JD-to-profile audit when available.
- Gate Ready to Apply on verification and quality checks.
- Keep Applied separate and evidence-based.
- Suppress duplicate notifications for superseded revisions.
