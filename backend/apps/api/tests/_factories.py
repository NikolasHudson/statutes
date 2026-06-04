"""Tiny test factories — keep test files focused on assertions, not setup."""

from __future__ import annotations

import datetime as dt
import hashlib

from apps.accounts.models import APIKey, Tier, User, generate_key
from apps.corpus.models import (
    Court,
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)


def make_iowa_caselaw_source() -> tuple[Source, NodeType, NodeType]:
    """The iowa-caselaw Source plus its decision/opinion NodeTypes, matching the
    0011 seed. Idempotent so multiple cases can share one source in a test."""
    j, _ = Jurisdiction.objects.get_or_create(
        slug="iowa", defaults={"name": "Iowa", "abbreviation": "IA"}
    )
    src, _ = Source.objects.get_or_create(
        jurisdiction=j,
        slug="iowa-caselaw",
        defaults={
            "name": "Iowa Caselaw",
            "citation_abbreviation": "Iowa",
            "official_url_template": (
                "https://www.courtlistener.com/opinion/{cl_cluster_id}/{slug}/"
            ),
        },
    )
    decision_t, _ = NodeType.objects.get_or_create(
        source=src, key="decision",
        defaults={"label_singular": "Decision", "label_plural": "Decisions",
                  "level": 1},
    )
    opinion_t, _ = NodeType.objects.get_or_create(
        source=src, key="opinion",
        defaults={"label_singular": "Opinion", "label_plural": "Opinions",
                  "level": 2},
    )
    return src, decision_t, opinion_t


# CourtListener slug → (name, authority level). Matches the 0011/Court seed.
_COURT_DEFAULTS = {
    "iowa": ("Supreme Court of Iowa", 1),
    "iowactapp": ("Court of Appeals of Iowa", 2),
}


def make_court(court_id: str = "iowa") -> Court:
    """The Court row a decision's ``court_id`` resolves to (name + level).
    Idempotent so many cases can share a court in one test."""
    j, _ = Jurisdiction.objects.get_or_create(
        slug="iowa", defaults={"name": "Iowa", "abbreviation": "IA"}
    )
    name, level = _COURT_DEFAULTS.get(court_id, (court_id, 1))
    court, _ = Court.objects.get_or_create(
        court_id=court_id,
        defaults={"name": name, "jurisdiction": j, "level": level},
    )
    return court


def make_caselaw_case(
    *,
    cl_cluster_id: int,
    cl_opinion_id: int,
    court_id: str = "iowa",
    precedential_status: str = "Published",
    body: str = "The opinion body.",
    case_name: str = "State v. Example",
    date_filed: str = "2020-01-01",
    docket_number: str = "",
    citations: list[str] | None = None,
    head_matter: str | None = None,
    with_version: bool = True,
) -> tuple[Node, Node, NodeVersion | None]:
    """One decision Node + one opinion child Node (+ its open APPROVED version),
    mirroring what ``ingest_iowa_caselaw`` writes. ``date_filed`` lands in the
    decision metadata (the browse list orders by it) and a matching Court row is
    ensured. Pass ``head_matter`` to add a head-matter version on the decision.
    Returns (decision_node, opinion_node, opinion_version)."""
    src, decision_t, opinion_t = make_iowa_caselaw_source()
    court = make_court(court_id)
    decision = Node.objects.create(
        source=src, node_type=decision_t, ordinal=str(cl_cluster_id),
        path=f"cl-cluster-{cl_cluster_id}", heading=case_name,
        source_metadata={
            "cl_cluster_id": cl_cluster_id,
            "court_id": court_id,
            "court_name": court.name,
            "precedential_status": precedential_status,
            "date_filed": date_filed,
            "docket_number": docket_number,
            "citations": list(citations or []),
        },
    )
    if head_matter:
        NodeVersion.objects.create(
            node=decision, body_text=head_matter,
            effective_from=dt.date.fromisoformat(date_filed),
            content_hash=hashlib.sha256(head_matter.encode()).hexdigest(),
            review_status=ReviewStatus.APPROVED,
        )
    opinion = Node.objects.create(
        source=src, node_type=opinion_t, parent=decision, ordinal="020",
        path=f"cl-cluster-{cl_cluster_id}/op-{cl_opinion_id}",
        heading="Lead Opinion",
        source_metadata={"cl_opinion_id": cl_opinion_id},
    )
    version = None
    if with_version:
        version = NodeVersion.objects.create(
            node=opinion, body_text=body,
            effective_from=dt.date.fromisoformat(date_filed),
            content_hash=hashlib.sha256(body.encode()).hexdigest(),
            review_status=ReviewStatus.APPROVED,
        )
    return decision, opinion, version


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
