#!/usr/bin/env bash
# Weekly refresh of the non-corpus reference datasets (RESOURCES_PLAN.md).
#
# Downloads the Iowa Secretary of State active-entity extract (~101 MB zipped),
# stages it, and applies it in one transaction: present rows are upserted,
# rows that stopped appearing are marked inactive with today's date. Nothing is
# ever deleted, and a file that is byte-identical to the last good load is
# skipped, so re-running this is free and safe.
#
# The load refuses, without touching the live table, if the file is under 90%
# of the current active row count or would deactivate more than 10% of it.
# That is the guard against a truncated publish; clear it deliberately with
# --force once you have looked at why the file shrank.
#
# Cron (droplet), running against whatever DB backend/.env points at:
#   23 6 * * 1  /home/dev/statutes/deploy/sync_resources_weekly.sh >> /home/dev/resource-syncs/cron.log 2>&1
#
# To target the production DB instead, export DATABASE_URL first — values
# already in the environment win over backend/.env (django-environ read_env
# only setdefault()s):
#   23 6 * * 1  DATABASE_URL='postgres://…' /home/dev/statutes/deploy/sync_resources_weekly.sh >> …
#
# NOT INSTALLED: like update_caselaw_daily.sh, the cron entry is Nick's call
# (cadence, and whether it runs here or on App Platform).
set -euo pipefail

BACKEND=/home/dev/statutes/backend
DATASET="${RESOURCE_DATASET:-iowa-business-entities}"

cd "$BACKEND"
exec .venv/bin/python manage.py sync_resource "$DATASET" "$@"
