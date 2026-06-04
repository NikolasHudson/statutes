"""Functional index for caselaw recency ordering + date-range filters.

A decision's filing date lives in ``source_metadata->>'date_filed'`` (a clean
10-char ISO ``YYYY-MM-DD`` string, so lexicographic order == chronological).
The existing ``node_source_metadata_gin`` is ``jsonb_path_ops`` — containment
(``@>``) only, useless for ordering or range. The browse "recent decisions"
list (``GET /api/browse/cases``) orders by date_filed DESC and supports a
date-range filter; without this index that's a full scan + sort of ~76k
decision rows.

Partial btree on the extracted text key, scoped to rows that carry the key
(only caselaw decisions do — opinions and statutes never set ``date_filed``),
so it stays small. Built ``CONCURRENTLY`` (hence ``atomic = False``) so it
doesn't take a long table lock against the live ``corpus_node`` table on prod;
instant on a fresh test DB.
"""

from django.db import migrations


CREATE_DATE_IDX = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS node_caselaw_date_filed
    ON corpus_node ((source_metadata->>'date_filed') DESC)
    WHERE source_metadata ? 'date_filed';
"""

DROP_DATE_IDX = """
DROP INDEX CONCURRENTLY IF EXISTS node_caselaw_date_filed;
"""


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("corpus", "0017_nodeversion_body_segments"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_DATE_IDX, reverse_sql=DROP_DATE_IDX),
    ]
