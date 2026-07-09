"""Rich rendering for assistant replies: citation links, HTML alternative,
and on-request official-PDF attachments.

Everything here is deterministic post-processing of the already-verified
answer — no LLM calls, so it adds no model cost and cannot change what the
answer *says*, only how it reads.

Linkification reuses the exact machinery the verification gate trusts:
``validate_citations`` (statute/rule cites with byte spans, resolved to
Nodes) and the citator's ``ReporterCitation`` table (reporter cite → decision
Node). Only citations that RESOLVE get links — an unresolvable cite stays
plain text, so a link is itself a small trust signal. Ambiguous reporter
triples (parallel reporters, table decisions) are left unlinked rather than
guessed, mirroring the resolver's own policy.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field

import requests
from markdown_it import MarkdownIt
from django.conf import settings

from apps.corpus.models import ReporterCitation, Source
from apps.corpus.services.lookups import official_url_for_node, validate_citations

logger = logging.getLogger(__name__)

# Statuses whose Node link is worth giving the reader (a repealed section's
# page shows its history + repeal, which is exactly what an attorney wants).
_LINKABLE = {"valid", "repealed"}

# Reporter cites the Iowa corpus can resolve: "759 N.W.2d 3", "48 Iowa 231",
# "199 N.W. 50". Negative lookahead keeps "2026 Iowa Code" out. Internal
# space tolerated in "N.W. 2d" (normalized before lookup).
_REPORTER_RE = re.compile(
    r"\b(\d{1,4})\s+(N\.W\.(?:\s?[23]d)?|Iowa(?!\s+Code))\s+(\d{1,5})\b"
)

_PDF_WANT_RE = re.compile(r"\bpdfs?\b", re.IGNORECASE)

MAX_PDF_ATTACHMENTS = 3
MAX_PDF_TOTAL_BYTES = 8_000_000  # Postmark's message cap is 10MB; leave headroom


@dataclass
class CitationLink:
    raw: str
    span: tuple[int, int]
    url: str
    official_url: str = ""


@dataclass
class LinkifiedAnswer:
    markdown: str  # answer with [cite](url) links injected
    sources: list[CitationLink] = field(default_factory=list)

    def sources_text(self) -> str:
        """Plaintext Sources block (the text/plain part gets no inline links)."""
        if not self.sources:
            return ""
        lines = ["", "Sources:"]
        for s in self.sources:
            line = f"- {s.raw}: {s.url}"
            if s.official_url:
                line += f" (official PDF: {s.official_url})"
            lines.append(line)
        return "\n".join(lines)

    def sources_markdown(self) -> str:
        if not self.sources:
            return ""
        lines = ["", "**Sources**", ""]
        for s in self.sources:
            line = f"- [{s.raw}]({s.url})"
            if s.official_url:
                line += f" — [official PDF]({s.official_url})"
            lines.append(line)
        return "\n".join(lines)


def _statute_links(content: str, base_url: str) -> list[CitationLink]:
    """Section/rule-shaped cites across every source, answer.py-style."""
    links: list[CitationLink] = []
    for source in Source.objects.all():
        try:
            report = validate_citations(content, source=source)
        except Exception:  # noqa: BLE001 — rendering must never sink a reply
            logger.exception("citation linkify failed for source %s", source.slug)
            continue
        for item in report.items:
            if item.status not in _LINKABLE or item.node is None:
                continue
            links.append(
                CitationLink(
                    raw=item.raw,
                    span=item.span,
                    url=f"{base_url}/section/{item.node.id}",
                    official_url=official_url_for_node(item.node)
                    if item.node.node_type.key == "section"
                    else "",
                )
            )
    return links


def _case_links(content: str, base_url: str) -> list[CitationLink]:
    links: list[CitationLink] = []
    for m in _REPORTER_RE.finditer(content):
        volume, reporter, page = m.group(1), m.group(2), m.group(3)
        reporter = reporter.replace(" ", "")
        node_ids = set(
            ReporterCitation.objects.filter(
                reporter=reporter, volume=volume, page=page, to_node__isnull=False
            ).values_list("to_node_id", flat=True)
        )
        if len(node_ids) != 1:  # unknown or ambiguous: leave it plain
            continue
        links.append(
            CitationLink(
                raw=m.group(0),
                span=(m.start(), m.end()),
                url=f"{base_url}/case/{node_ids.pop()}",
            )
        )
    return links


def linkify(content: str, *, base_url: str) -> LinkifiedAnswer:
    """Inject markdown links for every resolvable citation in ``content``."""
    candidates = _statute_links(content, base_url) + _case_links(content, base_url)

    # First claim wins on overlapping spans (a rules-source resolution of the
    # same substring, or a statute cite inside a longer match).
    claimed: list[tuple[int, int]] = []
    links: list[CitationLink] = []
    for link in sorted(candidates, key=lambda l: (l.span[0], -(l.span[1]))):
        start, end = link.span
        if any(s < end and start < e for s, e in claimed):
            continue
        # Already inside a markdown link the model wrote itself.
        if start > 0 and content[start - 1] in "[(":
            continue
        claimed.append((start, end))
        links.append(link)

    out = content
    for link in sorted(links, key=lambda l: l.span[0], reverse=True):
        start, end = link.span
        out = f"{out[:start]}[{link.raw}]({link.url}){out[end:]}"

    # Sources list: dedupe by target URL, keep first-appearance order.
    seen: set[str] = set()
    sources = []
    for link in sorted(links, key=lambda l: l.span[0]):
        if link.url in seen:
            continue
        seen.add(link.url)
        sources.append(link)
    return LinkifiedAnswer(markdown=out, sources=sources)


# ---------------------------------------------------------------------------
# HTML alternative
# ---------------------------------------------------------------------------


# CommonMark, because that's the dialect models actually emit: "1)" ordered
# lists and 2-space-nested bullets both render correctly (python-markdown
# handled neither — numbered lists collapsed into paragraph text). html=False
# makes the renderer escape any raw HTML in the model's output itself.
_MD = MarkdownIt("commonmark", {"html": False})


def _md_to_html(text: str) -> str:
    return _MD.render(text)


def render_html_body(answer_markdown: str, footer_lines: list[str]) -> str:
    """Left-aligned, client-default typography — it should read like a normal
    email sitting in a thread, not a styled newsletter (no max-width, no
    centering: a centered column looks broken once quoted replies stack up)."""
    body = _md_to_html(answer_markdown)
    footer = "<br>\n".join(html.escape(line) for line in footer_lines)
    return (
        f"<div>{body}</div>"
        '<hr style="border:none;border-top:1px solid #ddd;margin:16px 0 8px;">'
        f'<div style="font-size:12px;color:#666;">{footer}</div>'
    )


# ---------------------------------------------------------------------------
# Official-PDF attachments (only when the sender expressly asks)
# ---------------------------------------------------------------------------


def wants_pdf(question: str) -> bool:
    return bool(_PDF_WANT_RE.search(question or ""))


def official_pdf_attachments(
    question: str,
    *,
    limit: int = MAX_PDF_ATTACHMENTS,
    max_total_bytes: int = MAX_PDF_TOTAL_BYTES,
) -> list[tuple[str, bytes]]:
    """Fetch the official legis.iowa.gov PDFs for Iowa Code sections cited in
    the SENDER'S question (not the answer — 'send me the PDF of § 714.16'
    names its targets). Every candidate is fetched and sniffed; anything that
    isn't a real PDF is silently skipped. Caps keep a scattergun request from
    building a 10MB message."""
    attachments: list[tuple[str, bytes]] = []
    total = 0
    seen: set[int] = set()
    source = Source.objects.filter(slug="iowa-code").first()
    if source is None:
        return attachments
    report = validate_citations(question, source=source)
    for item in report.items:
        node = item.node
        if (
            node is None
            or item.status not in _LINKABLE
            or node.node_type.key != "section"
            or node.id in seen
        ):
            continue
        seen.add(node.id)
        url = official_url_for_node(node)
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=10)
        except requests.RequestException:
            logger.warning("official PDF fetch failed: %s", url)
            continue
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            logger.warning("official PDF not a PDF (%s): %s", resp.status_code, url)
            continue
        if total + len(resp.content) > max_total_bytes:
            break
        total += len(resp.content)
        attachments.append((f"Iowa Code {node.path}.pdf", resp.content))
        if len(attachments) >= limit:
            break
    return attachments
