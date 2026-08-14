# Career OS Control Center

A lightweight, responsive, dependency-free dashboard for the Career OS pipeline. It is intentionally a UI layer over the existing GitHub/Notion shared state; it does not duplicate or replace Truth Guard, Evidence Vault, Application Mode, or the browser executor.

## Current phase

- Responsive single-page control center
- Overview, Jobs, Applications, Resume Center, Review Queue, AI Agents, and Profile views
- Demo fallback so the UI is usable before live data sync is configured
- Live-data contract via `dashboard/data.json`
- No secrets in browser code

## Live deployment

The next deployment step is to publish this directory through GitHub Pages (or another static host) and have a server-side/GitHub Actions sync populate `data.json` from Notion. Notion credentials must never be placed in `app.js`, HTML, or any browser-visible asset.

## Safety

The dashboard is a control/visibility layer. It must never weaken Career OS Truth Guard, duplicate prevention, CAPTCHA/OTP handling, sensitive-question gates, or the verified-application confirmation requirement.
