"""Wire up search infrastructure for Phase 2.

Three things land here:

1. ``search_vector`` is populated automatically by Postgres triggers — one on
   ``NodeVersion`` (uses the row's body + a sub-select for heading) and one on
   ``Node`` (cascades heading edits down to all of the node's versions).
   Heading is weighted A, body weighted B.

2. Trigram GIN indexes on ``Node.heading`` and ``NodeVersion.body_text``
   make the fuzzy retriever fast.

3. Existing rows are backfilled by issuing a no-op UPDATE so the trigger
   computes their ``search_vector``.
"""

from django.db import migrations


SEARCH_VECTOR_FUNCTION = """
CREATE OR REPLACE FUNCTION corpus_nodeversion_search_vector_fn() RETURNS trigger AS $$
DECLARE
    heading_text text;
BEGIN
    SELECT heading INTO heading_text
    FROM corpus_node WHERE id = NEW.node_id;
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(heading_text, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.body_text, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

SEARCH_VECTOR_TRIGGER = """
DROP TRIGGER IF EXISTS corpus_nodeversion_search_vector ON corpus_nodeversion;
CREATE TRIGGER corpus_nodeversion_search_vector
    BEFORE INSERT OR UPDATE OF body_text, node_id ON corpus_nodeversion
    FOR EACH ROW EXECUTE FUNCTION corpus_nodeversion_search_vector_fn();
"""

NODE_HEADING_FUNCTION = """
CREATE OR REPLACE FUNCTION corpus_node_heading_cascade_fn() RETURNS trigger AS $$
BEGIN
    IF (NEW.heading IS DISTINCT FROM OLD.heading) THEN
        UPDATE corpus_nodeversion
        SET search_vector =
            setweight(to_tsvector('english', coalesce(NEW.heading, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(body_text, '')), 'B')
        WHERE node_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

NODE_HEADING_TRIGGER = """
DROP TRIGGER IF EXISTS corpus_node_heading_cascade ON corpus_node;
CREATE TRIGGER corpus_node_heading_cascade
    AFTER UPDATE OF heading ON corpus_node
    FOR EACH ROW EXECUTE FUNCTION corpus_node_heading_cascade_fn();
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS corpus_nodeversion_search_vector ON corpus_nodeversion;
DROP TRIGGER IF EXISTS corpus_node_heading_cascade ON corpus_node;
DROP FUNCTION IF EXISTS corpus_nodeversion_search_vector_fn();
DROP FUNCTION IF EXISTS corpus_node_heading_cascade_fn();
"""

# Backfill: a no-op UPDATE forces the BEFORE trigger to recompute search_vector
# for every existing row. Cheap; runs once at deploy time.
BACKFILL_SEARCH_VECTOR = """
UPDATE corpus_nodeversion SET body_text = body_text;
"""

CREATE_TRIGRAM_INDEXES = """
CREATE INDEX IF NOT EXISTS corpus_node_heading_trgm
    ON corpus_node USING gin (heading gin_trgm_ops);
CREATE INDEX IF NOT EXISTS corpus_nodeversion_body_text_trgm
    ON corpus_nodeversion USING gin (body_text gin_trgm_ops);
"""

DROP_TRIGRAM_INDEXES = """
DROP INDEX IF EXISTS corpus_node_heading_trgm;
DROP INDEX IF EXISTS corpus_nodeversion_body_text_trgm;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0004_widen_enacted_by"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SEARCH_VECTOR_FUNCTION + SEARCH_VECTOR_TRIGGER
            + NODE_HEADING_FUNCTION + NODE_HEADING_TRIGGER,
            reverse_sql=DROP_TRIGGERS,
        ),
        migrations.RunSQL(
            sql=BACKFILL_SEARCH_VECTOR,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CREATE_TRIGRAM_INDEXES,
            reverse_sql=DROP_TRIGRAM_INDEXES,
        ),
    ]
