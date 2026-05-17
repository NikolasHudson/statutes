"""Tiny test factories — keep test files focused on assertions, not setup."""

from __future__ import annotations

import datetime as dt
import hashlib

from apps.accounts.models import APIKey, Tier, User, generate_key
from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)


def make_user(email: str = "u@example.com", *, tier: str = Tier.SOLO) -> User:
    return User.objects.create_user(email=email, password="x", tier=tier)


def make_api_key(user: User, name: str = "test") -> tuple[APIKey, str]:
    """Return (APIKey instance, raw key). The raw key is what callers send
    in the X-API-Key header."""
    raw, prefix, hashed = generate_key()
    api_key = APIKey.objects.create(
        user=user, name=name, prefix=prefix, hashed_key=hashed
    )
    return api_key, raw


def make_iowa_corpus_minimal() -> tuple[Source, Node, NodeVersion]:
    """Just enough of Jurisdiction/Source/NodeType/Node/NodeVersion to test
    the API surface. Skips the data migration so tests run on an
    isolated TestCase without serialized_rollback."""
    j, _ = Jurisdiction.objects.get_or_create(
        slug="iowa", defaults={"name": "Iowa", "abbreviation": "IA"}
    )
    src, _ = Source.objects.get_or_create(
        jurisdiction=j,
        slug="iowa-code",
        defaults={
            "name": "Iowa Code",
            "citation_abbreviation": "Iowa Code",
            "official_url_template": (
                "https://www.legis.iowa.gov/docs/ico/section/{year}/{path}.pdf"
            ),
        },
    )
    chapter_t, _ = NodeType.objects.get_or_create(
        source=src,
        key="chapter",
        defaults={
            "label_singular": "Chapter",
            "label_plural": "Chapters",
            "abbreviation": "Ch.",
            "level": 2,
            "citation_segment_template": "ch. {ordinal}",
        },
    )
    section_t, _ = NodeType.objects.get_or_create(
        source=src,
        key="section",
        defaults={
            "label_singular": "Section",
            "label_plural": "Sections",
            "abbreviation": "§",
            "level": 3,
            "citation_segment_template": "§{ordinal}",
        },
    )
    chapter = Node.objects.create(
        source=src,
        node_type=chapter_t,
        ordinal="714",
        path="714",
        heading="Theft, fraud and related offenses",
    )
    section = Node.objects.create(
        source=src,
        node_type=section_t,
        parent=chapter,
        ordinal="16",
        path="714.16",
        heading="Consumer fraud",
    )
    body = (
        "A merchant who commits a deceptive practice or unfair method of "
        "competition violates this section. As used in this chapter, "
        "'merchant' means a person engaged in the business of selling "
        "goods or services."
    )
    version = NodeVersion.objects.create(
        node=section,
        body_text=body,
        effective_from=dt.date(2025, 1, 1),
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        review_status=ReviewStatus.APPROVED,
    )
    return src, section, version
