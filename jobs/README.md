# Career OS job inbox

Put one normalized job JSON file here when you want Career OS to process a vacancy.

Use the schema in `examples/job.json`:

```json
{
  "title": "Product Support Engineer",
  "company": "Example Company",
  "location": "Hyderabad, India",
  "url": "https://example.com/job",
  "source": "LinkedIn",
  "description": "Paste the complete job description here."
}
```

## Workflow

1. Find a vacancy on Scout, Jobright, Simplify, Huntr, LinkedIn, Indeed, a company career site, or another permitted source.
2. Copy the complete JD into a JSON file in this folder.
3. Run **GitHub → Actions → Career OS — Process Job → Run workflow**.
4. Career OS runs the JD/Fit Agent → Claude Resume Agent → Grok Challenger.
5. If the role is defensible, the full tailored resume and review information are written to the configured Notion review queue.
6. You review the job and resume in Notion and then apply manually using the source site / Simplify / Huntr.

Career OS intentionally does not auto-submit applications.
