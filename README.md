# Arcadian EU Deploy

Static landing page for [arcadian-eu.com](https://arcadian-eu.com), hosted on
DigitalOcean App Platform (app `arcadian-eu`, region `fra`).

## Layout

- `static-site/` — the whole site: EN at `/`, PL at `/pl/`, NL at `/nl/`,
  plus `/privacy/` and `/terms/` per locale. Pure HTML/CSS/JS, no build step.
- `.do/app.yaml` — the App Platform spec (source of truth; applied on every deploy).
- `.github/workflows/deploy.yml` — checks, deploy and post-deploy smoke test.

## Deployment — fully automatic

Push to `main` and GitHub Actions does the rest:

1. **checks** — `html-validate` over every page + `linkinator` crawls the site
   and verifies every internal and external link (also runs on pull requests).
2. **deploy** — `digitalocean/app_action` applies `.do/app.yaml` and deploys
   the static site. Spec changes (domains, ingress, …) ship the same way.
3. **smoke** — fetches the live pages of all three locales and posts a
   honeypot-flagged submission to the contact-form endpoint (werfvolt
   acknowledges it without storing a lead), proving the whole intake path.

One-time setup: a DigitalOcean API token with Apps read/write scope stored as
the `DIGITALOCEAN_ACCESS_TOKEN` repository secret. Nothing else is manual.

## Contact form

The form posts multipart directly to
`https://werfvolt.be/api/public/leads/form` — CORS-limited to
arcadian-eu.com, rate-limited and honeypotted on the werfvolt side, where it
is covered by tests. Attachments up to 100 MB (werfvolt's Caddy accepts 120 MB,
Spring 110 MB — keep the client limit below both). This repo holds no secrets.
