# Finalization implementation order

1. Stabilize validation and self-heal notifications.
2. Make raw discovery persistence unconditional and idempotent.
3. Make canonical Notion sync run from persisted candidates/results, including partial enrichment.
4. Add a deterministic daily web-discovery adapter using supported/public sources and preserve source evidence.
5. Persist the complete JD-to-profile audit in the canonical job record.
6. Validate the Ready-to-Apply gate end-to-end.
7. Add health/incident observability and single-incident notifications.
8. Run a scheduled soak test before production deployment.
9. Deploy the dashboard as the application front end only after the backend gates are green.

No stage should silently delete or skip a discovered job because an AI provider, enrichment step, or optional downstream integration is unavailable.
