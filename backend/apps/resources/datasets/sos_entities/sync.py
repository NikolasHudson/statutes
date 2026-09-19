"""Loader for the Iowa SOS active-business-entities extract.

Source: Iowa Data Hub dataset 554 (the catalog page calls it "Active Iowa
Business Entities"). Two facts about the feed shape everything here:

* the ``.csv`` URL serves a **ZIP** — ``BaseSync`` sniffs the magic bytes, so
  this module does not care;
* it is an **active-only** snapshot. Nothing in it says an entity dissolved;
  an entity simply stops appearing. The upsert-then-deactivate pass below is
  what turns that into history.

``ra_location`` / ``ho_location`` are deliberately not stored: they are
``POINT(lon lat)`` restatements of the latitude/longitude columns beside them.
"""

from __future__ import annotations

import datetime as dt

from apps.resources.normalize import normalize_name
from apps.resources.sync import BaseSync

from .models import BusinessEntity

# Columns the loader requires. Extra columns in the file are logged and
# ignored; a missing one aborts the run before anything is staged.
EXPECTED_COLUMNS = (
    "corp_number",
    "legal_name",
    "corporation_type",
    "effective_date",
    "registered_agent",
    "ra_address_1",
    "ra_address_2",
    "ra_city",
    "ra_state",
    "ra_zip",
    "ra_latitude",
    "ra_longitude",
    "home_office",
    "ho_address_1",
    "ho_address_2",
    "ho_city",
    "ho_state",
    "ho_zip",
    "ho_country",
    "ho_latitude",
    "ho_longitude",
)

LIVE_TABLE = BusinessEntity._meta.db_table
STAGING_TABLE = "_resources_sync_sos_entities"

# (column, postgres type) for the staging table, in COPY order. These are the
# columns the upsert carries across; bookkeeping columns (is_active, seen
# dates, snapshot) are supplied by the INSERT itself.
DATA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("corp_number", "varchar(12)"),
    ("legal_name", "varchar(255)"),
    ("name_normalized", "varchar(255)"),
    ("entity_type", "varchar(100)"),
    ("effective_date", "date"),
    ("registered_agent", "varchar(255)"),
    ("agent_normalized", "varchar(255)"),
    ("ra_address_1", "varchar(160)"),
    ("ra_address_2", "varchar(160)"),
    ("ra_city", "varchar(80)"),
    ("ra_state", "varchar(32)"),
    ("ra_zip", "varchar(16)"),
    ("home_office", "varchar(160)"),
    ("ho_address_1", "varchar(160)"),
    ("ho_address_2", "varchar(160)"),
    ("ho_city", "varchar(120)"),
    ("ho_state", "varchar(32)"),
    ("ho_zip", "varchar(16)"),
    ("ho_country", "varchar(16)"),
    ("ra_lat", "double precision"),
    ("ra_lon", "double precision"),
    ("ho_lat", "double precision"),
    ("ho_lon", "double precision"),
)

_NAMES = tuple(name for name, _ in DATA_COLUMNS)
_MAXLEN = {
    name: int(spec[len("varchar(") : -1])
    for name, spec in DATA_COLUMNS
    if spec.startswith("varchar(")
}

_STAGING_DDL = "CREATE TEMP TABLE {table} (\n  {cols}\n) ON COMMIT DROP".format(
    table=STAGING_TABLE,
    cols=",\n  ".join(f"{name} {spec}" for name, spec in DATA_COLUMNS),
)

# DISTINCT ON guards the upsert: ON CONFLICT DO UPDATE raises if one statement
# touches the same row twice, so a file that ever ships a duplicated key would
# otherwise take the whole load down.
_DEDUPED = (
    f"SELECT DISTINCT ON (corp_number) {', '.join(_NAMES)} "
    f"FROM {STAGING_TABLE} ORDER BY corp_number"
)

_UPSERT_SQL = """
INSERT INTO {live} ({cols}, is_active, first_seen, last_seen, deactivated_on,
                    last_snapshot_id)
SELECT {cols}, TRUE, %(today)s, %(today)s, NULL, %(snapshot)s
FROM ({deduped}) d
ON CONFLICT (corp_number) DO UPDATE SET
  {assignments},
  is_active = TRUE,
  last_seen = EXCLUDED.last_seen,
  deactivated_on = NULL,
  last_snapshot_id = EXCLUDED.last_snapshot_id
""".format(
    live=LIVE_TABLE,
    cols=", ".join(_NAMES),
    deduped=_DEDUPED,
    # first_seen is absent on purpose: it is the date we first saw the entity
    # and must survive every later load.
    assignments=",\n  ".join(
        f"{name} = EXCLUDED.{name}" for name in _NAMES if name != "corp_number"
    ),
)

_DEACTIVATE_SQL = f"""
UPDATE {LIVE_TABLE} e
   SET is_active = FALSE,
       deactivated_on = %(today)s,
       last_snapshot_id = %(snapshot)s
 WHERE e.is_active
   AND NOT EXISTS (
       SELECT 1 FROM {STAGING_TABLE} s WHERE s.corp_number = e.corp_number
   )
"""


def _trim(value: str | None, column: str) -> str:
    """Strip surrounding whitespace and clamp to the column width.

    The profile says every value fits with room to spare, but a source that
    quietly widens a field should cost us a truncated cell, not a failed load.
    """
    text = (value or "").strip()
    limit = _MAXLEN.get(column)
    return text[:limit] if limit else text


def _date(value: str | None) -> dt.date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class SosEntitiesSync(BaseSync):
    slug = "iowa-business-entities"
    source_url = "https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv"
    expected_columns = EXPECTED_COLUMNS
    # POINT(lon lat) restatements of the lat/lon columns beside them.
    ignored_columns = ("ra_location", "ho_location")

    staging_table = STAGING_TABLE
    staging_ddl = _STAGING_DDL
    staging_columns = _NAMES
    staging_key = "corp_number"

    def map_row(self, row: dict[str, str]) -> tuple | None:
        corp_number = _trim(row.get("corp_number"), "corp_number")
        if not corp_number:
            return None
        legal_name = _trim(row.get("legal_name"), "legal_name")
        agent = _trim(row.get("registered_agent"), "registered_agent")
        return (
            corp_number,
            legal_name,
            _trim(normalize_name(legal_name), "name_normalized"),
            _trim(row.get("corporation_type"), "entity_type"),
            _date(row.get("effective_date")),
            agent,
            _trim(normalize_name(agent), "agent_normalized"),
            _trim(row.get("ra_address_1"), "ra_address_1"),
            _trim(row.get("ra_address_2"), "ra_address_2"),
            _trim(row.get("ra_city"), "ra_city"),
            _trim(row.get("ra_state"), "ra_state"),
            _trim(row.get("ra_zip"), "ra_zip"),
            _trim(row.get("home_office"), "home_office"),
            _trim(row.get("ho_address_1"), "ho_address_1"),
            _trim(row.get("ho_address_2"), "ho_address_2"),
            _trim(row.get("ho_city"), "ho_city"),
            _trim(row.get("ho_state"), "ho_state"),
            _trim(row.get("ho_zip"), "ho_zip"),
            _trim(row.get("ho_country"), "ho_country"),
            _float(row.get("ra_latitude")),
            _float(row.get("ra_longitude")),
            _float(row.get("ho_latitude")),
            _float(row.get("ho_longitude")),
        )

    def live_active_count(self, cur) -> int:
        cur.execute(f"SELECT count(*) FROM {LIVE_TABLE} WHERE is_active")
        return cur.fetchone()[0]

    def plan_counts(self, cur, today: dt.date) -> dict[str, int]:
        cur.execute(
            f"""
            SELECT
              (SELECT count(DISTINCT corp_number) FROM {STAGING_TABLE}),
              (SELECT count(*) FROM ({_DEDUPED}) d
                 LEFT JOIN {LIVE_TABLE} e USING (corp_number)
                WHERE e.id IS NULL),
              (SELECT count(*) FROM ({_DEDUPED}) d
                 JOIN {LIVE_TABLE} e USING (corp_number)),
              (SELECT count(*) FROM ({_DEDUPED}) d
                 JOIN {LIVE_TABLE} e USING (corp_number)
                WHERE NOT e.is_active),
              (SELECT count(*) FROM {LIVE_TABLE} e
                WHERE e.is_active
                  AND NOT EXISTS (SELECT 1 FROM {STAGING_TABLE} s
                                   WHERE s.corp_number = e.corp_number))
            """
        )
        staged, inserted, updated, reactivated, deactivated = cur.fetchone()
        return {
            "staged": staged,
            "inserted": inserted,
            # Every staged row that already existed: a no-op rewrite counts
            # here too, since the source gives us no way to tell one apart.
            "updated": updated,
            "reactivated": reactivated,
            "deactivated": deactivated,
        }

    def apply(self, cur, snapshot, today: dt.date) -> None:
        params = {"today": today, "snapshot": snapshot.pk}
        cur.execute(_UPSERT_SQL, params)
        cur.execute(_DEACTIVATE_SQL, params)
