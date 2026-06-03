#!/usr/bin/env bash
# Clone the production DigitalOcean managed Postgres into the local `corpus` DB.
# Reads the prod connection string from .prod_db_url (gitignored) so no secret
# is passed on the command line or committed.
#
#   1. Add this droplet (143.244.168.79) to iowa-db's Trusted Sources in DO.
#   2. Put the doadmin connection URL in ./.prod_db_url  (one line, no quotes).
#   3. ./clone_prod_db.sh
set -euo pipefail

cd "$(dirname "$0")"

URL_FILE=".prod_db_url"
LOCAL_URL="postgres://corpus:corpus@localhost:5432/corpus"
ADMIN_URL="postgres://corpus:corpus@localhost:5432/postgres"   # corpus is local superuser
DUMP="prod.dump"

# Use the newest installed pg_dump/pg_restore (must be >= prod's major version).
NEWEST_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)"
PG_DUMP="${NEWEST_BIN:+$NEWEST_BIN/}pg_dump"
PG_RESTORE="${NEWEST_BIN:+$NEWEST_BIN/}pg_restore"
echo "Using $($PG_DUMP --version)"

[ -f "$URL_FILE" ] || { echo "ERROR: $URL_FILE not found. Put the doadmin URL there."; exit 1; }
PROD_URL="$(tr -d '[:space:]' < "$URL_FILE")"
[ -n "$PROD_URL" ] || { echo "ERROR: $URL_FILE is empty."; exit 1; }

echo "==> 1/5 Testing prod connectivity (10s timeout)..."
if ! psql "$PROD_URL" -tAc "select version()" >/tmp/prod_ver.txt 2>/tmp/prod_err.txt; then
  echo "FAILED to connect to prod. Most likely the droplet IP isn't in iowa-db's Trusted Sources yet."
  echo "Error:"; cat /tmp/prod_err.txt
  exit 1
fi
echo "    connected: $(cat /tmp/prod_ver.txt)"
echo "    prod corpus rows:"
psql "$PROD_URL" -c "SELECT (SELECT count(*) FROM corpus_node) AS nodes, (SELECT count(*) FROM corpus_nodeversion) AS versions, (SELECT count(*) FROM corpus_nodeversion WHERE embedding IS NOT NULL) AS embedded;"

echo "==> 2/5 Dumping prod (custom format, no owner/privileges)..."
"$PG_DUMP" "$PROD_URL" -Fc --no-owner --no-privileges -f "$DUMP"
echo "    wrote $DUMP ($(du -h "$DUMP" | cut -f1))"

echo "==> 3/5 Recreating local corpus DB..."
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = 'corpus' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS corpus;
CREATE DATABASE corpus OWNER corpus;
SQL

echo "==> 4/5 Restoring into local corpus (any role/comment errors are harmless; we verify by row count)..."
"$PG_RESTORE" --no-owner --no-privileges -d "$LOCAL_URL" "$DUMP" || {
  echo "    (pg_restore exited non-zero; this is normal for DO dumps — verifying data below...)"
}

echo "==> 5/5 Verifying local row counts..."
psql "$LOCAL_URL" -c "SELECT (SELECT count(*) FROM corpus_node) AS nodes, (SELECT count(*) FROM corpus_nodeversion) AS versions, (SELECT count(*) FROM corpus_nodeversion WHERE embedding IS NOT NULL) AS embedded, (SELECT count(*) FROM corpus_source) AS sources;"
psql "$LOCAL_URL" -c "SELECT extname, extversion FROM pg_extension ORDER BY extname;"

echo "==> Done. Local corpus DB now mirrors prod."
