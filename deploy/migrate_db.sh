#!/usr/bin/env bash
# One-time data migration: local Docker Postgres  ->  DO Managed Postgres.
#
# The stored embeddings (all ~29k NodeVersions) travel inside the dump, so
# there is NO re-embedding cost. Expect a few minutes for ~600 MB.
#
# Usage:
#   export TARGET_URL='postgresql://doadmin:PASS@db-host:25060/defaultdb?sslmode=require'
#   deploy/migrate_db.sh
#
# TARGET_URL is the *Managed Postgres* connection string from the DO panel
# (use the "VPC network" / public URI; keep sslmode=require).

set -euo pipefail

LOCAL_CONTAINER="${LOCAL_CONTAINER:-backend-db-1}"
LOCAL_DB="${LOCAL_DB:-corpus}"
LOCAL_USER="${LOCAL_USER:-corpus}"
PG_IMAGE="pgvector/pgvector:pg16" # client tools matched to the server major
DUMP="corpus_$(date +%Y%m%d_%H%M%S).dump"

if [[ -z "${TARGET_URL:-}" ]]; then
  echo "ERROR: set TARGET_URL to the Managed Postgres connection string." >&2
  exit 1
fi

echo "==> 1/5  Dumping ${LOCAL_DB} from container ${LOCAL_CONTAINER} ..."
docker exec "${LOCAL_CONTAINER}" \
  pg_dump -U "${LOCAL_USER}" -Fc --no-owner --no-privileges "${LOCAL_DB}" \
  > "${DUMP}"
echo "    wrote ${DUMP} ($(du -h "${DUMP}" | cut -f1))"

echo "==> 2/5  Enabling pgvector on the target ..."
docker run --rm -i "${PG_IMAGE}" \
  psql "${TARGET_URL}" -c 'CREATE EXTENSION IF NOT EXISTS vector;'

echo "==> 3/5  Restoring into the target (this is the long step) ..."
docker run --rm -i -v "$(pwd)/${DUMP}:/tmp/${DUMP}:ro" "${PG_IMAGE}" \
  pg_restore --no-owner --no-privileges --clean --if-exists \
  -d "${TARGET_URL}" "/tmp/${DUMP}"

echo "==> 4/5  Verifying row counts + embeddings on the target ..."
docker run --rm -i "${PG_IMAGE}" psql "${TARGET_URL}" -c "
  SELECT (SELECT count(*) FROM corpus_node)        AS nodes,
         (SELECT count(*) FROM corpus_nodeversion) AS versions,
         (SELECT count(*) FROM corpus_nodeversion
            WHERE embedding IS NOT NULL)            AS embedded,
         pg_size_pretty(pg_database_size(current_database())) AS size;"

echo "==> 5/5  Done."
cat <<'EOF'

Expected (from the source DB on 2026-05-17):
  nodes = 31002 | versions = 29062 | embedded = 29062

Next:
  * Confirm the counts above match.
  * The App Platform PRE_DEPLOY 'migrate' job (deploy/app.yaml) runs
    `manage.py migrate` automatically on deploy — restoring a full dump
    already includes the schema + the HNSW index, so migrate should report
    "No migrations to apply." If it instead wants to create tables, your
    TARGET_URL pointed at an empty DB and the restore did not land — re-run.
  * Spot-check search after deploy:
      GET https://<app>/api/lookup/714.16
EOF
