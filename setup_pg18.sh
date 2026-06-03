#!/usr/bin/env bash
# One-time privileged setup: install PostgreSQL 18 + pgvector to match prod
# (DO managed PG is 18.4), make it the cluster on port 5432, and (re)create the
# `corpus` superuser role + `corpus` database. Run with sudo:
#
#     sudo ./setup_pg18.sh
#
# Safe to re-run. The local PG16 cluster is EMPTY (schema only, no data) and is
# retired here; prod data lands in PG18 via clone_prod_db.sh afterwards.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo: sudo ./setup_pg18.sh"; exit 1; }

. /etc/os-release

echo "==> 1/5 Adding PGDG apt repo (${VERSION_CODENAME})..."
install -d /usr/share/postgresql-common/pgdg
curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list

echo "==> 2/5 Installing postgresql-18 + pgvector..."
apt-get update -qq
apt-get install -y postgresql-18 postgresql-18-pgvector

echo "==> 3/5 Retiring empty PG16 cluster (frees port 5432)..."
if pg_lsclusters -h | awk '{print $1,$2}' | grep -qx "16 main"; then
  pg_dropcluster --stop 16 main
fi

echo "==> 4/5 Moving PG18 cluster to port 5432..."
PG18_CONF=/etc/postgresql/18/main/postgresql.conf
pg_ctlcluster 18 main stop || true
if grep -qE '^[#[:space:]]*port[[:space:]]*=' "$PG18_CONF"; then
  sed -i -E 's/^[#[:space:]]*port[[:space:]]*=.*/port = 5432/' "$PG18_CONF"
else
  echo "port = 5432" >> "$PG18_CONF"
fi
pg_ctlcluster 18 main start

echo "==> 5/5 Creating corpus role + database..."
sudo -u postgres psql -p 5432 -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='corpus') THEN
    CREATE ROLE corpus LOGIN SUPERUSER PASSWORD 'corpus';
  ELSE
    ALTER ROLE corpus LOGIN SUPERUSER PASSWORD 'corpus';
  END IF;
END $$;
SQL
sudo -u postgres psql -p 5432 -tAc "SELECT 1 FROM pg_database WHERE datname='corpus'" | grep -q 1 \
  || sudo -u postgres createdb -p 5432 -O corpus corpus

echo "==> Verifying..."
pg_lsclusters
psql "postgres://corpus:corpus@localhost:5432/corpus" -tAc "select version()"
echo "==> Done. Now run (as your normal user):  ./clone_prod_db.sh"
