# Deploying to Heroku

The API runs on Heroku's container stack with Heroku Postgres. `heroku.yml`,
at the repo root, builds `api/Dockerfile` (with `api/` as the build context), and its release phase runs `alembic upgrade head`
before each new version starts; if a migration fails, the release is cancelled
and the previous version keeps serving.

One-time setup:

```bash
heroku create <app> --stack container
heroku addons:create heroku-postgresql:essential-0 -a <app>   # sets DATABASE_URL
heroku config:set APP_ENV=production \
  ALLOWED_ORIGINS=https://getaroomberkeley.me -a <app>
```

Deploy by pushing `main` to the `heroku` remote, from anywhere in the repo:

```bash
git push heroku main
```

Check `https://<app>.herokuapp.com/ready` afterwards; it returns 503 if the
database can't be reached.

A new database is empty, so the API returns no results until a term is
imported. Run the import from your own machine against the Heroku database
(see [Importing a term](importing.md) for `term create`'s arguments; a full term takes about
8-12 hours). Imports leave building coordinates empty, so set them afterwards or
the map shows no buildings (see [Building locations](building-locations.md)):

```bash
export DATABASE_URL=$(heroku config:get DATABASE_URL -a <app>)
python -m ingestion.cli term create --name "Fall 2026" ...
caffeinate -is python -m ingestion.cli import run "Fall 2026"
python -m ingestion.cli buildings set-locations
```
