# Career OS Job Capture Extension

This is a Manifest V3 Chrome extension for capturing a job posting and sending it into Career OS without storing a GitHub token in the extension.

## What it does

1. Open a job posting.
2. Click the Career OS extension.
3. Review/edit title, company, location and the captured job description.
4. Click **Send to Career OS**.
5. The extension opens a GitHub issue in the Career-OS repository and fills the full machine-readable job payload.
6. Click **Submit new issue**.
7. The `career-os-job-intake` GitHub Action commits the job JSON and runs the existing multi-agent pipeline.
8. Career OS writes the review and tailored resume to Notion when configured.

The extension deliberately requires the final GitHub **Submit new issue** click. This keeps job intake human-controlled and avoids putting a GitHub personal access token inside a browser extension.

## Install locally in Chrome

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Choose **Load unpacked**.
4. Select this `extension/` folder from the cloned Career-OS repository.
5. Pin **Career OS Job Capture**.

## Notes

- Generic job-page extraction is best-effort. Always review the captured JD before submitting.
- Some sites restrict browser scripts or render the JD dynamically; in those cases paste/correct the description in the popup.
- The extension does not auto-submit applications and does not bypass site access controls.
