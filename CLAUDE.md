# Deployment notes

Hosted on Render (free tier), with Supabase Postgres as `DATABASE_URL` (also backs APScheduler's job store in [scheduler.py](scheduler.py)). UptimeRobot pings `/health` periodically to reduce cold-sleep frequency.

## Reminders are fired by an external poller, not by the app itself

`scheduler.py`'s `BackgroundScheduler` is started paused (`scheduler.start(paused=True)`) — its own timer thread never fires anything. This is deliberate: on 2026-08-21 that thread silently stopped processing due jobs in production with nothing logged, and needed a manual restart to flush them. `add_job`/`remove_job` still write straight through to the jobstore while paused, so scheduling itself (from webhook handlers) is unaffected.

The only thing that actually fires a due reminder is `scheduler.run_due_jobs()`, exposed at `/run-due-reminders`. **A second UptimeRobot monitor (separate from the `/health` one) hits this URL every 5 minutes** — this lives entirely in the UptimeRobot dashboard, not in this repo, so there's nothing here to grep for to confirm it exists. If reminders stop arriving, check that monitor is still active and pointed at the right URL before assuming a code regression — `/health` staying green says nothing about whether reminders are being processed.

## Render's "Start Command" must match the Procfile

Render's dashboard has its own **Start Command** field (Settings → Start Command) that, if set, silently overrides [Procfile](Procfile) — Render will not fall back to the Procfile even if you clear the field back to blank (it requires a non-empty value).

On 2026-08-21 this field had drifted to a bare `gunicorn app:app`, discarding the Procfile's `--timeout 120 --workers 1 --worker-class gthread --threads 4`. The app ran fine, so this went unnoticed for a while — it just meant gunicorn silently fell back to its own defaults (`sync` worker, 30s timeout) instead of the cold-start resilience settings the Procfile was written for.

[render.yaml](render.yaml) now declares the same `startCommand` so it can be managed from git instead of the dashboard going forward. This only takes effect once the existing Render service is linked to it (Dashboard → Blueprints → New Blueprint Instance → point at this repo; Render matches the existing service by the `name` in render.yaml and offers to adopt it rather than create a duplicate — do this once, and **review the proposed diff before confirming**, since Render will apply anything render.yaml declares to the live service). After that one-time link, changing the start command is just an edit to render.yaml + a git push. Until it's linked, the dashboard field is still the one in effect, and still needs manual updates to match the Procfile.
