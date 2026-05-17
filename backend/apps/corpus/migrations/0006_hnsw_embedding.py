"""HNSW index on the embedding column for fast approximate nearest neighbour.

We use ``vector_cosine_ops`` because we score with cosine distance — Voyage's
embeddings are already L2-normalized so cosine and inner-product order matches,
but cosine is the conventional choice for legal text similarity.

HNSW build parameters are left at pgvector defaults (m=16, ef_construction=64).
We can tune these once the corpus is loaded and we have eval numbers.
"""

from django.db import migrations


CREATE_HNSW = """
CREATE INDEX IF NOT EXISTS corpus_nodeversion_embedding_hnsw
    ON corpus_nodeversion USING hnsw (embedding vector_cosine_ops);
"""

DROP_HNSW = """
DROP INDEX IF EXISTS corpus_nodeversion_embedding_hnsw;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("corpus", "0005_search_indexes"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_HNSW, reverse_sql=DROP_HNSW),
    ]
