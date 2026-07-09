#!/usr/bin/env bash
# Daily CourtListener incremental update (caselaw Phase 5).
#
# Sweeps cases CL added since the last successful run (cursor stored in
# ingestion_caselaw.IngestionRun) and runs the full ingest → citations →
# display → xref → chunk → embed chain. Everything is idempotent, so a
# crashed or overlapping run is safe to just re-run.
#
# Cron (droplet), running against whatever DB backend/.env points at:
#   17 11 * * *  /home/dev/statutes/deploy/update_caselaw_daily.sh >> /home/dev/cl-updates/cron.log 2>&1
#
# To target the production DB instead, export DATABASE_URL first — values
# already in the environment win over backend/.env (django-environ read_env
# only setdefault()s):
#   17 11 * * *  DATABASE_URL='postgres://…' /home/dev/statutes/deploy/update_caselaw_daily.sh >> …
#
# The first-ever run needs a start point: pass it through, e.g.
#   ./update_caselaw_daily.sh --since 2026-03-27
set -euo pipefail

BACKEND=/home/dev/statutes/backend
OUT="${CL_UPDATE_OUT:-/home/dev/cl-updates}"

cd "$BACKEND"
exec .venv/bin/python manage.py update_iowa_caselaw --out-dir "$OUT" "$@"
