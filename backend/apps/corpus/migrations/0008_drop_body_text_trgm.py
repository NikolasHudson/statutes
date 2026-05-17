"""Drop the now-unused trigram index on NodeVersion.body_text.

``trigram_search`` no longer fuzzy-matches body text (see the docstring in
services/search.py): a GIN trigram index over full statute bodies matched
most of the corpus at any recall-friendly threshold and the heap recheck
recomputed similarity() over megabytes — a fixed ~10 s full-scan per search.
With body trigram gone the index is dead weight: it serves no query yet is
maintained on every NodeVersion write. The matching CREATE lives in 0005, so
its forward SQL is the reverse here (and vice-versa) to keep 0005 reversible.
"""

from django.db import migrations


DROP = "DROP INDEX IF EXISTS corpus_nodeversion_body_text_trgm;"
RECREATE = (
    "CREATE INDEX IF NOT EXISTS corpus_nodeversion_body_text_trgm "
    "ON corpus_nodeversion USING gin (body_text gin_trgm_ops);"
)


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0007_seed_iowa_court_rules"),
    ]

    operations = [
        migrations.RunSQL(sql=DROP, reverse_sql=RECREATE),
    ]
