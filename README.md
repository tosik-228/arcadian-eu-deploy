# Arcadian EU Deploy

Static landing page for [arcadian-eu.com](https://arcadian-eu.com), hosted on
DigitalOcean App Platform (app `arcadian-eu`, region `fra`).

## Layout

- `static-site/` — the whole site: EN at `/`, PL at `/pl/`, NL at `/nl/`,
  plus `/privacy/` and `/terms/` per locale. Pure HTML/CSS/JS with one
  deterministic build step that injects the public Turnstile sitekey.
- `.do/app.yaml` — the App Platform spec (source of truth; applied on every deploy).
- `.github/workflows/deploy.yml` — checks, deploy and post-deploy smoke test.

## Deployment — fully automatic

Push to `main` and GitHub Actions does the rest:

1. **checks** — validates the contact-form JavaScript, builds the site with a
   non-working CI-only placeholder, runs `html-validate` over every page and
   uses `linkinator` to verify every internal and external link (also on pull requests).
2. **deploy** — `digitalocean/app_action` applies `.do/app.yaml` and deploys
   the static site. Spec changes (domains, ingress, …) ship the same way.
3. **smoke** — fetches the live pages of all three locales and posts a
   honeypot-flagged submission to the contact-form endpoint (werfvolt
   acknowledges it without storing a lead), proving the whole intake path.

One-time GitHub repository setup:

- `DIGITALOCEAN_ACCESS_TOKEN` secret — DigitalOcean API token with Apps read/write scope;
- `TURNSTILE_SITEKEY` Actions variable — the public Cloudflare Turnstile sitekey
  registered for `arcadian-eu.com` and `www.arcadian-eu.com`.

The workflow refuses to deploy if either value is absent or if the sitekey has
an unsafe format.

## Contact form

The form posts multipart directly to
`https://werfvolt.be/api/public/leads/form` — CORS-limited to
arcadian-eu.com, rate-limited and honeypotted on the werfvolt side, where it
is covered by tests. Attachments are capped at 50 MiB, matching the Werfvolt
multipart admission boundary.

All three localized forms explicitly render Cloudflare Turnstile with action
`arcadian_contact`. Submission remains disabled until Turnstile supplies the
`cf-turnstile-response` field. The widget is reset after every attempted HTTP
submission because tokens are single-use; loading, configuration, expiry and
verification failures keep the form closed.

`static-site/build-turnstile-site.sh` requires `TURNSTILE_SITEKEY`, verifies
that exactly three source widgets contain the deploy placeholder, and writes
the configured site to the ignored `static-site/dist/` directory. A local
configuration-injection check can use any synthetic value that matches the
documented character constraints; it will not produce a working widget:

```sh
TURNSTILE_SITEKEY=local_only_invalid_sitekey sh static-site/build-turnstile-site.sh
```

For an actual browser check, use a sitekey registered for the local test
hostname. Do not put the Turnstile secret key in this repository, App Platform
spec or browser code. Server-side token verification and its secret belong only
to the Werfvolt backend.

Rollout order is deliberate: deploy this site with the configured public sitekey first; the old
backend ignores the extra token. Then enable server-side verification and confirm that both a real
verified submission and the honeypot smoke path behave correctly. This repo holds no secrets.
