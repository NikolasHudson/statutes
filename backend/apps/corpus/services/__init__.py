"""Service layer between callers (views, MCP handlers, ingestion) and the ORM.

Keep direct ORM access out of views and MCP handlers — call functions defined
in submodules so cache layers, audit logging, and access controls slot in
cleanly.

Submodules:
    embeddings — queue and run the embedding job over NodeVersion rows
    search     — FTS, trigram, vector, and RRF-fused hybrid retrieval
    voyage     — thin client wrapping the Voyage AI embedding API
"""

from . import embeddings, lookups, query_expansion, search, voyage  # noqa: F401
