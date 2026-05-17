"""Resolve a parsed Citation to a Node.

Lookup goes through Node.path, which is the materialized citation path.
Subdivisions inside the section body are not yet stored as separate Nodes
(Phase 1 keeps section as the leaf), so resolution stops at the section.
"""

from __future__ import annotations

from apps.corpus.models import Node, Source

from .parser import Citation


def resolve(citation: Citation, source: Source) -> Node | None:
    """Return the matching Node, or None. Never guesses."""
    target_path = citation.section_path or citation.chapter_path
    return Node.objects.filter(source=source, path=target_path).first()
