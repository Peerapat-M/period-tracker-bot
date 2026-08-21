# Deployment notes

Hosted on Render (free tier), with Supabase Postgres as `DATABASE_URL` (also backs APScheduler's job store in [scheduler.py](scheduler.py)). UptimeRobot pings `/health` periodically to reduce cold-sleep frequency.

## Render's "Start Command" must match the Procfile

Render's dashboard has its own **Start Command** field (Settings → Start Command) that, if set, silently overrides [Procfile](Procfile) — Render will not fall back to the Procfile even if you clear the field back to blank (it requires a non-empty value).

On 2026-08-21 this field had drifted to a bare `gunicorn app:app`, discarding the Procfile's `--timeout 120 --workers 1 --worker-class gthread --threads 4`. The app ran fine, so this went unnoticed for a while — it just meant gunicorn silently fell back to its own defaults (`sync` worker, 30s timeout) instead of the cold-start resilience settings the Procfile was written for.

[render.yaml](render.yaml) now declares the same `startCommand` so it can be managed from git instead of the dashboard going forward. This only takes effect once the existing Render service is linked to it (Dashboard → Blueprints → New Blueprint Instance → point at this repo; Render matches the existing service by the `name` in render.yaml and offers to adopt it rather than create a duplicate — do this once, and **review the proposed diff before confirming**, since Render will apply anything render.yaml declares to the live service). After that one-time link, changing the start command is just an edit to render.yaml + a git push. Until it's linked, the dashboard field is still the one in effect, and still needs manual updates to match the Procfile.
