# Deployment

The site is live at **https://getaroomberkeley.me**, served by GitHub Pages.
It's a static build, so all it needs is the API's address, the term to search
and a Mapbox token, which are all built into the page.

## Where it's served

- Pages' source is **GitHub Actions** (repo Settings → Pages), and the custom
  domain `getaroomberkeley.me` is set there too. **Enforce HTTPS** is on, and
  `www.getaroomberkeley.me` redirects to the bare domain.
- DNS is at the domain's registrar: four `A` records for `@` pointing to
  GitHub Pages' addresses (185.199.108.153 to 185.199.111.153), and a `CNAME`
  for `www` pointing to `lewisyang3.github.io`.

## How a deploy happens

A push to `main` that changes `web/` deploys. CI (`.github/workflows/web.yml`,
at the repo root) runs the `check` job
(lint, format check, type check, tests, build), and if it passes, the `deploy`
job builds the site with the repository variables below and publishes `dist/`.
Pull requests and other branches only run the checks.

A newer push to `main` doesn't cancel a deploy that's under way; it waits for
it to finish.

## Repository variables

Set under Settings → Secrets and variables → Actions → Variables. What each
one does is under [Configuration](development.md#configuration).

| Variable            | Production value                                    |
| ------------------- | --------------------------------------------------- |
| `VITE_API_BASE_URL` | `https://get-a-room-api-65b3f2ee7cbb.herokuapp.com` |
| `VITE_TERM_ID`      | `1` (Fall 2026)                                     |
| `VITE_MAPBOX_TOKEN` | A public Mapbox token (`pk.…`)                      |

Find the production term's id by running `python -m ingestion.cli term list`
in `api/` with `DATABASE_URL` set to the Heroku database (see the API's
[Deploying to Heroku](../../api/docs/deployment.md)).

The values are built into the page, so changing one has no effect until the
site is deployed again.

## Redeploying without a code change

After changing a variable, for example to point `VITE_TERM_ID` at a new term,
run the Web workflow by hand. In GitHub, open it under Actions and choose
**Run workflow** on `main`, or from a terminal:

```bash
gh workflow run web.yml --ref main
```

## Visitor counts

[GoatCounter](https://www.goatcounter.com) counts visitors, without cookies,
through the script tag in `index.html`. The dashboard is at
**https://lewisyang.goatcounter.com**. The site is a single page, so each visit
is one page view.

- Ad blockers stop the script, so the count runs low, probably by 10–30%.
- Visits from `localhost` aren't counted, so local and Docker runs don't
  inflate it.

## The API side

Browsers only accept the API's responses if the API lists the site's address
in `ALLOWED_ORIGINS`. Production sets it to `https://getaroomberkeley.me`
(`www` redirects, so it doesn't need its own entry). Setting up and deploying
the API is covered in the API's
[Deploying to Heroku](../../api/docs/deployment.md).
