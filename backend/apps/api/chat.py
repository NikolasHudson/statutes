"""OpenAI-powered chat endpoint.

The server runs an OpenAI tool-calling loop against the corpus tool
implementations and returns the final assistant message plus a trace of the
tool calls so a human can verify the answer was grounded in Iowa Code lookups.

Auth: Django session — the caller MUST be a logged-in user. The endpoint
spends *our* ``OPENAI_API_KEY`` (settings, from env), so it is gated by a
per-user daily message cap and a global monthly hard ceiling. These two
counters are the only thing between us and an unbounded OpenAI bill; in
production they live in Redis (see settings.CACHES) so they hold across
processes and deploys.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.api.accounts import _require_login
from apps.api.paywall import require_paid_access
from apps.api.session_auth import session_auth
from apps.api.trace_capture import record_chat_trace
from apps.api.usage import (
    FEATURE_CHAT,
    collect_usage,
    emit_completion_usage,
    enforce_token_budget,
)
from apps.tenancy.entitlement import is_entitled
from apps.corpus.models import Node, NodeVersion, ReviewStatus, Source
from apps.corpus.services.lookups import current_version
from apps.corpus.services.corpus_tools import (
    _today,
    get_cross_references_tool,
    get_definitions_tool,
    get_section_at_date_tool,
    get_version_history_tool,
    list_recent_amendments_tool,
    lookup_citation_tool,
)
from apps.corpus.services.retrieval import (
    RetrievedContext,
    RetrievedPassage,
    _excerpt,
    retrieve_context,
    treatment_payload,
)
from apps.corpus.services.answer import (
    abstain_decision,
    render_advisory,
    should_abstain,
    verify_answer,
)
from apps.corpus.services import semantic_support
from apps.corpus.services.premise import (
    check_premises,
    finding_dicts,
    render_premise_caution,
)


# Max body text returned per search hit, in chars. The MCP tool caps at 280
# chars; for the chat surface we want enough text that the LLM can usually
# answer "what are the requirements" from a single search call without a
# follow-up lookup. 2000 chars ≈ a typical short Iowa Code section.
SEARCH_BODY_MAX_CHARS = 2000

# The top reranked hit(s) get a much larger budget. The dispositive
# limitation on a rule is frequently in its Comments, not its black-letter
# text — e.g. Iowa Ct. R. 32:1.10's Comments (which start ~char 2270) are
# what scope the screening exception to lateral-hire conflicts. Cutting at
# 2000 chars hands the model the rule's conditions with none of the official
# commentary that bounds them, and it then over-generalizes from training
# priors. A handful of long top hits is a price worth paying for that.
SEARCH_BODY_MAX_CHARS_TOP = 9000
TOP_HITS_FULL = 2


# Retrieve a wide candidate pool from hybrid search, then let the reranker
# pick the few that actually answer the question. Returning 18 loosely-related
# sections (the old behaviour) buried the on-point rule in noise; a tight,
# reranked set is what makes the answer — and its source list — trustworthy.
#
# Pool size 100 (PR2, was 50): a cross-encoder reranker only helps if the
# on-point answer is in the pool it sees, and decision-cluster dedup + MMR need
# headroom below the display cut. The shared pipeline caps each candidate's
# rerank text at 8000 chars, so a 100-opinion caselaw pool stays affordable.
CHAT_CANDIDATE_POOL = 100
CHAT_DISPLAY_LIMIT = 6


def _search_with_context(args: dict) -> tuple[dict, RetrievedContext | None]:
    """Chat's search: delegate to the shared ``retrieve_context`` pipeline and
    return BOTH the serialized chat-hit result and the underlying
    ``RetrievedContext`` (whose passages carry the PR3 treatment flags).

    The chat loop keeps the contexts for the turn so the final verify/abstain
    gate can cross-reference the drafted answer against what was actually
    retrieved (stale-use detection). ``None`` is returned for the empty-query
    short-circuit, where no retrieval happened.

    ``source_slug`` is injected by the chat endpoint from the request-level
    source picker, not chosen by the model — scoping is a user decision. The
    model's ``limit`` is intentionally ignored: chat noise is a precision
    problem, not a recall one. Reranks the full candidate pool down to the
    display set, then attaches a long ``body_excerpt`` (from the current
    version) and the section's ``effective_from`` so the model can quote the
    real effective date instead of fabricating one (today's date written as
    "Effective from …" was a common hallucination tell)."""
    query = args["query"]
    if not query or not query.strip():
        return (
            {
                "query": query,
                "hits": [],
                "as_of_date": _today(),
                "error": "query must not be empty",
            },
            None,
        )
    ctx = retrieve_context(
        query,
        source_slug=args.get("source_slug"),
        use_vector=args.get("use_vector", True),
        candidate_pool=CHAT_CANDIDATE_POOL,
        display_limit=CHAT_DISPLAY_LIMIT,
        rerank=True,
        enrich_bodies=True,
        excerpt_budget_top=SEARCH_BODY_MAX_CHARS_TOP,
        excerpt_budget_rest=SEARCH_BODY_MAX_CHARS,
        top_hits_full=TOP_HITS_FULL,
    )
    # PR4: surface the abstain signal to the model (advisory). The system prompt
    # tells it to be candid when no good-law authority was found instead of
    # stretching an adjacent rule. Additive — existing keys are unchanged.
    ctx.abstain, ctx.abstain_reason = should_abstain(ctx)
    payload = {
        "query": ctx.query,
        "hits": [
            {
                "node": p.node_dict,
                "snippet": p.snippet,
                "score": p.score,
                "component_scores": p.component_scores,
                # An attorney-curated research note (scope/currency guidance)
                # must not compete for attention as a sibling metadata field —
                # prepend it to the excerpt the model actually reads.
                "body_excerpt": (
                    f"⚠ RESEARCH NOTE (read first): {p.node_dict['research_note']}"
                    f"\n\n{p.excerpt}"
                    if p.node_dict.get("research_note")
                    else p.excerpt
                ),
                "effective_from": p.effective_from,
                # PR2: matched caselaw passage offsets into the opinion body
                # (None for statutes) — lets a UI highlight the exact span.
                "char_start": p.char_start,
                "char_end": p.char_end,
                # PR3: good-law / treatment flag (advisory). status "negative"
                # means a citing case overruled/abrogated/superseded it.
                "treatment": treatment_payload(p.treatment),
            }
            for p in ctx.passages
        ],
        "as_of_date": ctx.as_of_date,
        # PR4 (additive): whole-result abstain signal for this search.
        "abstain": ctx.abstain,
        "abstain_reason": ctx.abstain_reason,
    }
    return payload, ctx


def _enriched_search(args: dict) -> dict:
    """Chat's search tool as registered in ``TOOL_HANDLERS`` — the serialized
    result only. The loop calls :func:`_search_with_context` directly when it
    needs to also capture the context for the turn's verify/abstain gate."""
    return _search_with_context(args)[0]


def _merge_turn_context(
    contexts: list[RetrievedContext],
) -> RetrievedContext | None:
    """Collapse every ``search_statutes`` context from a turn into one, so the
    final gate sees all retrieved authority. Passages are deduped by
    ``cluster_id`` (a decision/section appears once even if several searches
    surfaced it), keeping the first occurrence. Returns ``None`` only when the
    turn ran no search at all — the signal the abstain gate uses to NOT block a
    lookup-only / pinned-document answer for an empty search set. An empty-but-
    present context (a search that genuinely returned nothing) is preserved."""
    if not contexts:
        return None
    merged: list[RetrievedPassage] = []
    seen: set[int] = set()
    for ctx in contexts:
        for p in ctx.passages:
            if p.cluster_id in seen:
                continue
            seen.add(p.cluster_id)
            merged.append(p)
    queries = " | ".join(dict.fromkeys(c.query for c in contexts if c.query))
    return RetrievedContext(
        query=queries,
        passages=merged,
        as_of_date=contexts[0].as_of_date,
    )


def _premise_guard(
    messages: list[dict[str, Any]], source_slug: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """PR6 (anti-anchoring): verify the case-holding premises the user asserts in
    the latest question against the retrieved opinions, BEFORE the model drafts.

    Returns ``(caution_system_text, premise_problem_dicts)``. Two orthogonal axes,
    independently gated:

    * **Currency** (``RAG_CURRENCY_CHECK``, default ON): is the named case still
      good law? Deterministic — needs no OpenAI key — so it runs by default and
      catches the faithful-reading-of-an-overruled-case trap.
    * **Fidelity** (``RAG_PREMISE_CHECK``, default off): does the case hold what
      the user says? An LLM round-trip, so it only runs when on AND a key resolves
      a checker.

    A no-op ``("", [])`` only when BOTH are off. The caution is injected as a
    system message so the model corrects the premise instead of parroting it; the
    dicts ride into the final advisory."""
    currency_on = getattr(settings, "RAG_CURRENCY_CHECK", True)
    fidelity_on = getattr(settings, "RAG_PREMISE_CHECK", False)
    if not (currency_on or fidelity_on):
        return "", []
    # The checker drives the fidelity axis only; currency reads the deterministic
    # treatment flag and runs with checker=None.
    checker = semantic_support.default_checker() if fidelity_on else None
    last_user = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    if not last_user.strip():
        return "", []
    findings = check_premises(
        last_user, source_slug=source_slug, checker=checker, currency=currency_on
    )
    if not findings:
        return "", []
    return render_premise_caution(findings), finding_dicts(findings)


chat_router = Router()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatMessage(Schema):
    role: str  # "user" | "assistant" | "system"
    content: str


# Models a logged-in user is allowed to spend our key on. Keeping this tight
# is a cost control: an unrestricted `model` field would let any session pick
# the most expensive model. Add to this set deliberately, not by request.
ALLOWED_CHAT_MODELS = {"gpt-4o-mini", "gpt-4o", "gpt-5-mini"}
DEFAULT_CHAT_MODEL = "gpt-5-mini"


class ChatRequest(Schema):
    messages: list[ChatMessage]
    model: str = DEFAULT_CHAT_MODEL
    # Optional corpus scope (e.g. "iowa-court-rules"). None searches all
    # sources. Forced into every search_statutes call; the model cannot
    # override it.
    source_slug: str | None = None
    # Optional: pin the conversation to a single document — a statute section /
    # court rule node, or a caselaw decision node. When set, that document's
    # current text is injected as authoritative context so the model answers
    # about it directly, while still free to use the tools for cross-references.
    node_id: int | None = None


class ToolCallTrace(Schema):
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class ChatResponse(Schema):
    content: str
    tool_calls: list[ToolCallTrace]
    model: str


# ---------------------------------------------------------------------------
# Tool registry — maps OpenAI function names to corpus tool callables.
# Tool schemas mirror the MCP surface so the LLM has the same affordances.
# ---------------------------------------------------------------------------


TOOL_HANDLERS = {
    "lookup_citation": lambda args: lookup_citation_tool(
        args["citation"], source_slug=args.get("source_slug")
    ),
    "search_statutes": _enriched_search,
    "get_version_history": lambda args: get_version_history_tool(args["section_id"]),
    "get_section_at_date": lambda args: get_section_at_date_tool(
        args["section_id"], args["on_date"]
    ),
    "get_cross_references": lambda args: get_cross_references_tool(args["section_id"]),
    "get_definitions": lambda args: get_definitions_tool(
        args["term"], chapter=args.get("chapter")
    ),
    "list_recent_amendments": lambda args: list_recent_amendments_tool(
        args["since"], limit=args.get("limit", 50)
    ),
}


OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_citation",
            "description": (
                "Look up a precise Iowa Code citation. Never fuzzy. "
                "Examples: '714.16', '714.16(2)(a)', 'Iowa Code § 232.2', "
                "'I.C. 12C.3', 'chapter 232'. Returns the full section text, "
                "official URL, effective date, and version metadata. If "
                "ambiguous, returns candidate sections instead of guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "citation": {
                        "type": "string",
                        "description": "The citation string to resolve.",
                    }
                },
                "required": ["citation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_statutes",
            "description": (
                "Hybrid search across the corpus (full-text + trigram + "
                "vector, RRF-fused, then reranked for relevance). Use for "
                "natural-language questions, topic searches, or when the user "
                "does not have a specific citation. Returns a small, curated "
                "set of the most on-point sections — each with a body_excerpt "
                "(up to ~2000 chars) you should read and summarize. Prefer one "
                "focused query over many broad ones; the result is already "
                "reranked, so do not ask for a large limit to 'see more'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "use_vector": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_version_history",
            "description": "Full amendment history for a section (by node id).",
            "parameters": {
                "type": "object",
                "properties": {"section_id": {"type": "integer"}},
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_section_at_date",
            "description": (
                "Point-in-time view of a section: the version that was in "
                "effect on a specific ISO date (YYYY-MM-DD)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_id": {"type": "integer"},
                    "on_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["section_id", "on_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cross_references",
            "description": (
                "Outgoing and incoming cross-references for a section "
                "(both 'this section references X' and 'X references this')."
            ),
            "parameters": {
                "type": "object",
                "properties": {"section_id": {"type": "integer"}},
                "required": ["section_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_definitions",
            "description": (
                "Find statutory definitions of a term. Optionally restrict "
                "to a single chapter (e.g. chapter='714')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "chapter": {"type": "string"},
                },
                "required": ["term"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_amendments",
            "description": "Sections amended on or after the given ISO date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "since": {"type": "string", "description": "YYYY-MM-DD"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["since"],
            },
        },
    },
]


SYSTEM_PROMPT = (
    "You are an Iowa legal research assistant. Always call a tool before "
    "answering substantive legal questions — never rely on training-data "
    "recall for statute text.\n\n"
    "How to answer:\n"
    "1. If the user gives a citation, call lookup_citation. Drop the "
    "reporter-name words ('Iowa Code §', 'Iowa Ct. R.', 'Iowa R. Civ. "
    "P. ...') but pass the rule/section number EXACTLY as numbered, "
    "INCLUDING any chapter prefix. Iowa Court Rules are numbered with a "
    "'<chapter>:' prefix — pass '32:1.10' or '32:1.10(a)', NOT a "
    "stripped '1.10' (which mis-resolves to the Iowa Code and fails). "
    "Iowa Code sections have no such prefix: '714.16', '1.421(4)'.\n"
    "2. If the user asks a topical question, call search_statutes. The "
    "results include a body_excerpt with up to ~2000 chars of the section "
    "text. Read it and answer from it.\n"
    "2a. A multi-part question needs a SEPARATE search/lookup per part. "
    "'Deadline to move' and 'deadline to answer after the motion is denied' "
    "are different rules — do not answer the second from the first rule's "
    "text. Search again with terms for the part you haven't grounded yet.\n"
    "2b. Every hit carries a 'chapter' ({ordinal, heading}) and 'division'. "
    "USE them to reject out-of-context hits: a question about a District "
    "Court trial is governed by the Rules of Civil/Criminal Procedure, NOT "
    "the Rules of Appellate Procedure. If the only hit that matches your "
    "keywords is from the wrong chapter, it is not your answer — search "
    "again with better terms.\n"
    "3. If a body_excerpt is truncated (ends with '…') or does not fully "
    "answer the question, call lookup_citation for that specific section to "
    "get its complete text BEFORE answering. Do not answer from a partial "
    "excerpt when the missing part is what was asked. For professional-"
    "conduct / ethics rules especially, the dispositive limitation on an "
    "exception is often in the rule's official Comments, not its black-"
    "letter text — if the excerpt is truncated before or within the "
    "Comments, fetch the full rule before concluding an exception "
    "applies.\n"
    "3a. FOLLOW CROSS-REFERENCES THAT GOVERN A FACT IN PLAY. Retrieved "
    "statutory text routinely delegates the operative rule to a neighbor "
    "('public notice … as provided in section 21.4', 'except as provided "
    "in section X'). When the delegated subject matters to the user's "
    "facts — an UNANNOUNCED meeting makes the notice section the very "
    "heart of the case — lookup_citation the referenced section and ground "
    "the answer in ITS text. Citing the section that points to the rule, "
    "while never reading the rule, leaves out the provision an attorney "
    "would actually litigate under.\n\n"
    "Your answer must summarize what the statute actually says — list the "
    "requirements, conditions, exceptions, deadlines, etc. Do NOT just hand "
    "the user a citation and a link; that is unhelpful. Quote short phrases "
    "where they're load-bearing.\n\n"
    "VOICE: write like a research memo to a licensed attorney, in the "
    "register of the law itself. NEVER surface your tooling in the answer: "
    "no 'tool output', 'search results', 'retrieved text', 'treatment/"
    "excerpt fields', 'per developer instructions', and no checklist "
    "narrating your own research process. State holdings assertively as "
    "legal facts with citations — 'Garrison overruled Gacke's three-part "
    "test and applied rational basis review' — never as descriptions of "
    "your database ('the tool output lists Gacke as overruled'). When a "
    "treatment flag says a case was overruled, retrieve the overruling "
    "opinion and state what the court actually DID and held; only if you "
    "cannot retrieve it may you say that later authority reports the "
    "overruling, without metadata language. An attorney reading the memo "
    "must see law, not plumbing. Concretely BANNED in answers: opening with "
    "a 'Checklist' of your process; the words 'retrieved', 'tool', 'search "
    "result', 'treatment note/flag', 'excerpt field'; parentheticals like "
    "'(search_statutes done)' or '(as retrieved)'. Begin directly with the "
    "short answer.\n\n"
    "GROUNDING RULES — these are absolute:\n"
    "• RESEARCH NOTES: when a tool result carries a ``research_note`` field, "
    "it is attorney-curated guidance about that authority's SCOPE or "
    "currency (e.g. which fact patterns a statute excludes, or that a case "
    "was superseded). Read it FIRST and apply the authority only within the "
    "bounds the note describes; if the note excludes the user's fact "
    "pattern, say so plainly and cite the note's supporting authority.\n"
    "• Never state a rule/section number, deadline, day-count, dollar amount, "
    "or any other specific that does not appear verbatim in a tool result. "
    "Words like 'typically', 'often', 'usually', or 'such as 10 days' before "
    "a specific are a sign you are guessing — stop and call a tool instead.\n"
    "• Do not claim a rule 'governs' or 'also governs' a sub-question unless "
    "that rule's own retrieved text actually addresses it. Stretching the "
    "initial-response rule to cover a post-ruling deadline it never mentions "
    "is a hallucination.\n"
    "• STATUTORY SILENCE IS NOT PERMISSION: the absence of a limitation in a "
    "statute's text is NOT authority that the limitation doesn't exist. "
    "'Section 625.22 does not say the fee clause must be mutual, therefore "
    "mutuality is not required' is an ungrounded assertion — no tool result "
    "says it, so you may not say it. When a party seeks a BENEFIT (fees, "
    "damages, a remedy), identify affirmative authority ENTITLING them — "
    "the contract's own terms, a statute granting the right, or a case "
    "awarding it to a similarly-situated party. Fee-shifting is the classic "
    "trap: § 625.22 only taxes fees the CONTRACT entitles the winner to; a "
    "clause running solely to the other party gives your client nothing, "
    "and Iowa has no reciprocity statute. If you find no authority "
    "entitling the client, say that plainly.\n"
    "• DOMAIN FIT: before relying on an authority, check that its own act or "
    "chapter governs this fact pattern's subject matter — the chapter heading "
    "in the tool result tells you. A real, accurately-quoted section from the "
    "WRONG body of law is still a wrong answer: Iowa Code ch. 554 (Uniform "
    "Commercial Code) governs sales of goods and commercial transactions, NOT "
    "residential leases — a lease's liquidated-damages or deposit question is "
    "governed by ch. 562A (residential landlord-tenant), not § 554.2718. When "
    "the fact pattern's own act has an on-point provision, search for and "
    "cite THAT provision instead of a neighboring-domain analogue. If no "
    "on-domain provision exists and you reason by analogy from another "
    "domain, SAY it is an analogy that does not directly govern.\n"
    "• When a retrieved rule makes an exception, cure, or safe harbor "
    "available ONLY under a stated condition, quote that condition and "
    "check it against the specific facts the user gave before telling them "
    "the exception applies. If the facts do not satisfy the condition, say "
    "the exception is NOT available and explain which condition fails. "
    "Example: a screening exception conditioned on the conflict arising "
    "from a 'prior firm' does not apply to a conflict created inside the "
    "lawyer's current firm. Recognizing that an exception exists is not "
    "the same as confirming it applies here.\n"
    "• If the retrieved text does not answer part of the question, say so "
    "explicitly ('the retrieved text of Rule X does not address Y'), do one "
    "more targeted search for that part, and only if it still cannot be "
    "found, say you could not locate the governing rule. Never fill the gap "
    "from memory or with an unrelated rule.\n"
    "• If a lookup_citation fails or returns found:false, tell the user you "
    "could not retrieve that provision and try search_statutes; never "
    "substitute a remembered rule number.\n"
    "• Never invent an ``official_url`` or an ``effective_from`` date. Use "
    "the values that appear in the tool result for that section, verbatim. "
    "If a section is mentioned in the answer but no tool result resolved it, "
    "OMIT the link and the effective date rather than synthesise plausible-"
    "looking ones. Telltale hallucinations: today's date written as an "
    "'effective from' date, or a tidy URL like "
    "``legis.iowa.gov/docs/iac/rule/32.1.18.pdf`` that you wrote rather than "
    "copied — both are wrong.\n"
    "• Cite each section using its canonical path form — the ``path`` field "
    "of the node (e.g. ``1.981``, ``32:1.10``, ``714.16``) — prefixed by the "
    "source's abbreviation (``Iowa Ct. R. 1.981``, ``Iowa Code § 714.16``). "
    "Do NOT split the path across words (``Chapter 1, Rule 981`` is wrong; "
    "``Iowa Ct. R. 1.981`` is right). The first time you cite a section, use "
    "the full form so the reader can verify it.\n\n"
    "CASELAW: the corpus also includes Iowa court decisions (opinions), not "
    "only statutes and rules. search_statutes returns these too — it matches "
    "by reporter citation (e.g. '763 N.W.2d 862') and party name as well as "
    "by topic. (lookup_citation is for statute/rule citations only; to pull a "
    "specific case, search_statutes with its citation or name.) When a result "
    "is a case, the same grounding rules apply: state a holding only where the "
    "retrieved opinion text supports it, quote short load-bearing phrases, and "
    "cite the case by its name and reporter citation EXACTLY as they appear in "
    "the result (the heading / case_name and any ``citations``) — never invent "
    "a reporter, volume, page, or year. Use cases to illustrate or interpret a "
    "statute/rule, but the governing authority for a statutory question is "
    "still the statute or rule itself.\n\n"
    "GOOD LAW: each search hit carries a ``treatment`` flag. When its "
    "``status`` is ``negative`` (a later Iowa case ``overruled`` / "
    "``abrogated`` / ``superseded`` it — see ``treatment.label``, "
    "``by_citation``, and the verbatim ``treatment.excerpt``), do NOT rely on "
    "that case as good law: say plainly that it was treated negatively, name "
    "the case that did so, and find current authority instead. A ``status`` of "
    "``caution`` (e.g. ``overruled-on-other-grounds``) means the case survives "
    "for the point you are citing but was qualified on another — note the "
    "limitation if it bears on the question. The flag is advisory and "
    "phrase-derived; if it conflicts with the opinion text you retrieved, say "
    "so rather than asserting a conclusion.\n\n"
    "APPLYING A STATUTE TO FACTS — elements, terms of art, exclusions: "
    "before advising that a statute applies (and ESPECIALLY before advising "
    "someone to plead it), do three checks. (1) Test EVERY conjunctive "
    "element against the facts: 'sold AND served' is two requirements, and "
    "a convenience-store carry-out sale satisfies only one. (2) Treat "
    "statutory words as terms of art, not ordinary English: whether a "
    "counter sale is 'serving', whether an occupant is a 'tenant', whether "
    "a seller is a 'merchant' has usually been construed by Iowa's "
    "appellate courts — run ONE more search combining the section number "
    "with the user's fact keywords ('123.92 convenience store carry-out "
    "off-premises') and read how courts applied the section to comparable "
    "facts; a construing case that EXCLUDES the fact pattern IS the "
    "answer. (3) Hunt for what the statute excludes as hard as what it "
    "includes: definitions, provisos, 'shall not be liable' clauses, and "
    "licensee-class distinctions routinely immunize actors the operative "
    "clause seems to cover. Keyword overlap between the statute and the "
    "facts is not applicability.\n"
    "VOLUNTEERED STRATEGY must meet the same grounding bar as the direct "
    "answer. If you go beyond the user's question to suggest tactics — "
    "filing a separate suit, splitting relief across two actions or tracks, "
    "dismissing and refiling, holding a claim back for later — FIRST check "
    "the doctrines that police those moves (claim preclusion and the rule "
    "against claim-splitting for parallel/serial suits arising from one "
    "transaction; compulsory counterclaims; election of remedies; "
    "jurisdictional and amount limits) by searching for them like any other "
    "proposition. 'File a separate suit for the injunction while the "
    "damages case proceeds' is malpractice bait when res judicata bars "
    "splitting one transaction into two actions. If you have not grounded "
    "a tactic, omit it or say explicitly that it requires a claim-"
    "preclusion check — never present an unverified workaround as a safe "
    "path.\n"
    "AUTHORITY HIERARCHY: when several retrieved authorities establish the "
    "same point, LEAD with the controlling one — the Iowa Supreme Court over "
    "the Court of Appeals, and the overruling/landmark opinion itself over a "
    "later case that merely describes it. Citing a Court of Appeals summary "
    "as your primary authority for what the Supreme Court held reads as "
    "secondhand research; cite the Supreme Court case first and use the "
    "lower-court case, if at all, as a see-also application.\n"
    "USER-SUPPLIED AUTHORITY: when the USER cites a case as controlling "
    "('under Godfrey...', 'relying on Frohwein...'), do NOT accept its "
    "currency from the user. Before relying on it, run one additional "
    "search_statutes for its subsequent treatment — query the case name plus "
    "'overruled OR superseded OR abrogated' — and read what later decisions "
    "did to it. A landmark case is exactly the kind most likely to have been "
    "overruled or superseded by statute; the user citing it does not make it "
    "good law, and confirming a stale premise is worse than correcting it.\n\n"
    "ABSTAIN: a search result carries an ``abstain`` flag (with "
    "``abstain_reason``). When it is true — nothing on point was retrieved, or "
    "every authority found has been negatively treated — say plainly that you "
    "could not locate good-law Iowa authority on that point and do one more "
    "targeted search; do NOT stretch an off-point or overruled source to fill "
    "the gap. It is better to tell the user no current authority was found than "
    "to manufacture a confident answer from bad law.\n\n"
    "When the tool result for a section includes a non-empty "
    "``official_url`` and / or ``effective_from``, carry their VALUES into "
    "your answer verbatim alongside that section's citation — but render "
    "them as prose, never as raw field syntax: write '(official text: "
    "<url>)' and '(effective January 1, 2025)', NOT 'official_url:' or "
    "'effective_from: 2025-01-01'. Field names are database plumbing; an "
    "attorney's memo shows dates and links, not schema. When either field "
    "is missing or empty in the tool output, OMIT it — do not write "
    "anything in its place. Today's date is not a substitute for an "
    "effective date; a guessed URL is not a substitute for the official "
    "one. If a citation is ambiguous, present the candidates and ask the "
    "user to pick — never silently substitute.\n\n"
    "PROFESSIONAL CONDUCT / ETHICS RULES — additional checks (chapter 32, "
    "44, 45, 51):\n"
    "• MANDATORY vs PERMISSIVE: ethics rules routinely have both a 'shall' "
    "branch and a 'may' branch in the same section. Before quoting the "
    "permissive language, check the mandatory branch first against the "
    "specific facts. Withdrawal is the classic trap: 32:1.16(a) MANDATES "
    "withdrawal when continuing the representation would result in a "
    "violation of the rules or other law (e.g. assisting client crime or "
    "fraud under 32:1.2(d)); 32:1.16(b) PERMITS withdrawal when 'withdrawal "
    "can be accomplished without material adverse effect on the interests "
    "of the client'. If the facts trigger 32:1.16(a)(1), do NOT pull the "
    "32:1.16(b) 'no material adverse effect' boilerplate — withdrawal is "
    "required regardless of effect on the client. Same pattern for "
    "disclosure under 32:1.6(b) (all permissive), 32:1.13(c) (permissive "
    "report-out), and 32:3.3 (mandatory candor to the tribunal).\n"
    "• TIMELINE — has the triggering event ALREADY happened? Read the facts "
    "for tense before choosing the duty. Prospective misconduct ('client "
    "wants me to offer a forged document') = the duty is to REFUSE "
    "(32:3.3(a)(3)) and counsel the client. But if the false material is "
    "ALREADY before the tribunal (attached to a filed petition, already "
    "testified to, already produced), a fraud on the tribunal has already "
    "occurred and 32:3.3(b) makes remedial measures MANDATORY now — "
    "remonstrate, seek correction, and if necessary disclose, and the "
    "client cannot veto this (32:3.3(c) overrides confidentiality). If the "
    "client forbids remediation (or threatens the lawyer for pursuing it), "
    "the lawyer CANNOT comply with the rules while continuing, so "
    "withdrawal is MANDATORY under 32:1.16(a)(1) — do NOT tell the lawyer "
    "they 'may possibly remain' by declining to use the document going "
    "forward; that answer ignores the fraud already in the record, and "
    "withdrawal alone may not even satisfy 32:3.3(b).\n"
    "• Keep distinct doctrines separate. 'Noisy withdrawal' (the lawyer "
    "withdraws AND disaffirms documents or opinions previously delivered to "
    "prevent a third party from being defrauded — rooted in the Comment to "
    "32:1.6 and cross-referenced in 32:1.2 Comment) is NOT the same as "
    "'reporting out' under 32:1.13(c) (revealing organizational confidences "
    "when the entity's highest authority fails to act and a violation is "
    "reasonably certain to result in substantial injury TO THE "
    "ORGANIZATION). When the fraud harms an outside party (a bank, a "
    "buyer, a counterparty), the lawyer's authority to disclose comes from "
    "32:1.6(b)(2) or (b)(3), NOT from 32:1.13(c). Do not cite 32:1.13(c) "
    "to justify disclosure to an outsider.\n"
    "• Comments are not the black-letter rule. When you rely on a Comment, "
    "label it as 'Comment [N] to Rule X' — do not present its language as "
    "if it were the rule's operative text. The black letter and the "
    "Comments can say materially different things; mixing them creates "
    "false authority.\n\n"
    "MULTI-ISSUE QUESTIONS — completeness is mandatory:\n"
    "• Before searching, restate every distinct sub-question the user asked "
    "as an explicit checklist. Count each numbered item, AND each separately "
    "requested kind of authority (e.g. 'cite the Rule of Civil Procedure', "
    "'the Iowa Code section', 'controlling Supreme Court / Court of Appeals "
    "authority') as its own checklist entry.\n"
    "• Retrieve for ALL checklist entries. When entries are independent, "
    "issue their searches/lookups as parallel tool calls in a SINGLE turn "
    "rather than one per round — you have a limited number of rounds, so "
    "breadth per round is how you cover everything in time.\n"
    "• Structure the final answer as one clearly labeled section per "
    "sub-question, in the user's original order. Never merge two "
    "sub-questions into one paragraph and never drop one.\n"
    "• End every multi-issue answer with a one-line coverage check that "
    "names any sub-question you could not fully ground. If you could not "
    "verify a part, say so in its own section and give the best grounded "
    "analysis you can from what you retrieved — an explicit, flagged "
    "best-effort answer is required; silent omission is not acceptable."
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


MAX_TOOL_LOOPS = 10

# On the final allowed round we stop offering tools and force the model to
# answer from whatever it has already retrieved. This turns a broad,
# multi-issue question (which legitimately needs many retrievals) into a
# grounded best-effort answer instead of a hard 500 that discards the trace.
SYNTHESIS_NUDGE = (
    "You have used your retrieval budget for this turn. Do not ask for more "
    "tools. Answer now using only the sources already gathered in this "
    "conversation. Address EVERY numbered question and every separately "
    "requested kind of authority from the user's message, in their original "
    "order, as its own clearly labeled section — do not merge or drop any. "
    "Cite the specific provisions you found. For any sub-question the "
    "gathered sources do not fully resolve, give the best grounded analysis "
    "you can and mark that section clearly as needing verification. Finish "
    "with a one-line coverage check listing any sub-question left unverified."
)

# A complete multi-issue legal analysis is long; give the model enough room
# so the forced final answer is never cut off mid-section.
ANSWER_MAX_TOKENS = 4000

# Reasoning-tier models spend *hidden* reasoning tokens that count against
# the same output budget as the visible answer. With ANSWER_MAX_TOKENS=4000
# and the default `reasoning_effort='medium'`, gpt-5-mini routinely exhausts
# its budget on reasoning before producing any visible content — the
# response returns with empty `content` and a successful 200. Two things
# fix this together: (1) a much larger token budget, since reasoning eats
# most of it; (2) `reasoning_effort='low'` so the model doesn't chain-of-
# thought at length on top of the structured work the tool loop is already
# doing. Names listed here are the OpenAI base IDs; the API also serves
# dated variants like `gpt-5-mini-2025-08-07` whose first 11 chars match,
# so we substring-test below.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
REASONING_ANSWER_MAX_TOKENS = 16000


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in REASONING_MODEL_PREFIXES)


def _model_extras(model: str) -> dict[str, Any]:
    """Per-model kwargs layered onto the chat-completions call. Empty for
    classic chat models; reasoning models get `reasoning_effort='low'`."""
    if _is_reasoning_model(model):
        return {"reasoning_effort": "low"}
    return {}


def _token_budget(model: str) -> int:
    return REASONING_ANSWER_MAX_TOKENS if _is_reasoning_model(model) else ANSWER_MAX_TOKENS


def _create_completion(client, base_kwargs: dict, max_tokens: int, state: dict):
    """Create a chat completion, tolerant of the OpenAI output-token param
    rename. Newer / reasoning models reject 'max_tokens' and require
    'max_completion_tokens'; older models and some compatible proxies only
    accept 'max_tokens'. We probe once, then lock in whatever the BYO model
    accepts so later rounds don't re-pay the 400. Only the token-param
    incompatibility is retried — auth/quota/other errors propagate at once."""
    strategies = state.get("strategies", ["max_completion_tokens", "max_tokens", None])
    last_exc: Exception | None = None
    for strat in list(strategies):
        kwargs = dict(base_kwargs)
        if strat is not None:
            kwargs[strat] = max_tokens
        try:
            completion = client.chat.completions.create(**kwargs)
            state["strategies"] = [strat]  # remember the one that worked
            return completion
        except Exception as exc:
            msg = str(exc).lower()
            is_token_param = (
                "unsupported_parameter" in msg or "unsupported parameter" in msg
            ) and ("max_tokens" in msg or "max_completion_tokens" in msg)
            # Classic models reject reasoning_effort; non-prefixed reasoning
            # variants may reject some efforts. Strip the field and retry
            # rather than 502 — losing the effort hint is a degradation, not
            # a failure.
            is_reasoning_param = (
                "unsupported_parameter" in msg or "unsupported parameter" in msg
            ) and "reasoning_effort" in msg
            if is_reasoning_param and "reasoning_effort" in base_kwargs:
                base_kwargs = {k: v for k, v in base_kwargs.items() if k != "reasoning_effort"}
                last_exc = exc
                continue
            # Same defensive strip for stream_options (usage accounting on
            # streams): an OpenAI-compatible proxy that predates it must
            # degrade to "no usage recorded", never to a failed chat.
            is_stream_options_param = (
                "unsupported_parameter" in msg or "unsupported parameter" in msg
            ) and "stream_options" in msg
            if is_stream_options_param and "stream_options" in base_kwargs:
                base_kwargs = {k: v for k, v in base_kwargs.items() if k != "stream_options"}
                last_exc = exc
                continue
            if is_token_param:
                last_exc = exc
                continue
            raise
    assert last_exc is not None
    raise last_exc


def _scope_preamble(source_slug: str | None) -> str:
    """Extra system-prompt text pinning the assistant to one corpus, so it
    frames answers ("under the Iowa Court Rules…") and does not reach for
    out-of-scope sources."""
    if not source_slug:
        return ""
    name = (
        Source.objects.filter(slug=source_slug)
        .values_list("name", flat=True)
        .first()
    )
    label = name or source_slug
    return (
        f"\n\nSCOPE: This conversation is restricted to {label}. "
        f"Every search_statutes call is filtered to that source. Answer only "
        f"from it; if it does not address the question, say so plainly rather "
        f"than guessing from another body of law. For professional-conduct / "
        f"ethics scenarios under the Iowa Court Rules, chapter 32 (Rules of "
        f"Professional Conduct) governs."
    )


# Cap on how much of a pinned document we inject verbatim. Statute sections sit
# comfortably under this; long multi-opinion decisions get truncated and the
# model is told to fall back to the search tools for the remainder.
DOC_CONTEXT_MAX_CHARS = 24000


def _decision_text(node: Node) -> tuple[str, str]:
    """``(header, body)`` for a caselaw decision node: a one-line caption plus
    each child opinion's currently effective, approved text, concatenated.
    Mirrors how ``apps/api/browse.py`` assembles the case detail."""
    md = node.source_metadata
    bits = [f"Case: {node.heading}"]
    for key in ("court_name", "date_filed"):
        if md.get(key):
            bits.append(md[key])
    cites = md.get("citations") or []
    if cites:
        bits.append("; ".join(cites))
    header = " · ".join(bits)

    opinions = list(
        Node.objects.filter(parent=node, node_type__key="opinion").order_by(
            "ordinal", "path"
        )
    )
    versions = {
        v.node_id: v
        for v in NodeVersion.objects.filter(
            node__in=opinions,
            effective_to__isnull=True,
            review_status=ReviewStatus.APPROVED,
        )
    }
    parts: list[str] = []
    for op in opinions:
        ver = versions.get(op.id)
        if ver and ver.body_text.strip():
            label = op.heading or op.source_metadata.get("type") or "Opinion"
            parts.append(f"--- {label} ---\n{ver.body_text.strip()}")
    if not parts:
        # No separate opinions (or none approved) — fall back to the decision's
        # own head-matter version, which sometimes carries the combined text.
        head = current_version(node)
        if head and head.body_text.strip():
            parts.append(head.body_text.strip())
    return header, "\n\n".join(parts)


def _provision_text(node: Node) -> tuple[str, str]:
    """``(header, body)`` for a statute section or court-rule node."""
    citation = f"{node.source.citation_abbreviation} {node.path}".strip()
    header = f"{citation} — {node.heading}" if node.heading else citation
    version = current_version(node)
    return header, (version.body_text if version else "")


def _pinned_document(node_id: int | None) -> str | None:
    """Assemble the verbatim text of a single pinned document for injection as
    a system message. Returns the message content, or None when there is no
    ``node_id`` or the node has no current approved content to show."""
    if not node_id:
        return None
    node = (
        Node.objects.select_related("source", "node_type", "parent")
        .filter(pk=node_id)
        .first()
    )
    if node is None:
        return None

    if node.node_type.key == "decision":
        header, body = _decision_text(node)
    else:
        header, body = _provision_text(node)
    if not body.strip():
        return None

    if len(body) > DOC_CONTEXT_MAX_CHARS:
        body = (
            body[:DOC_CONTEXT_MAX_CHARS].rstrip()
            + "\n\n[document truncated — use the search tools for the remainder]"
        )

    return (
        "PINNED DOCUMENT — the user is reading this document, and their "
        "questions are about it unless they clearly say otherwise. Treat the "
        "text below as authoritative, already-retrieved context: answer "
        "directly from it without searching for it again. You may still use the "
        "tools to pull cross-referenced authorities, definitions, amendment "
        "history, or anything this document cites. When you rely on it, quote it "
        "exactly and cite it.\n\n"
        f"{header}\n\n{body}"
    )


def _bump(cache_key: str, timeout: int) -> int:
    """Atomically increment a quota counter, initialising it to 1 on first
    use. Mirrors apps/api/auth.py's rate-limit accounting so both quota
    surfaces behave identically against the shared (Redis in prod) cache."""
    try:
        return cache.incr(cache_key)
    except ValueError:
        # Race: two requests both miss the key. add() is atomic and only one
        # wins; the loser then sees the established value via incr().
        if cache.add(cache_key, 1, timeout=timeout):
            return 1
        return cache.incr(cache_key)


def _enforce_chat_quota(user) -> None:
    """Per-user daily cap + a global monthly hard ceiling. Raises 429 when
    either is exceeded. Counters are incremented up front so an in-flight
    OpenAI tool loop still counts against the budget — the whole point is
    that this endpoint spends our money, not the caller's."""
    # Dollar budgets first (they don't consume anything): a budget-capped
    # request must not burn one of the user's daily message-count slots.
    enforce_token_budget(user)

    now = timezone.now()

    global_key = f"chat:global:{now:%Y-%m}"
    global_used = _bump(global_key, timeout=40 * 86_400)
    if global_used > settings.CHAT_MONTHLY_GLOBAL_LIMIT:
        raise HttpError(
            503,
            "The assistant is temporarily unavailable (monthly capacity "
            "reached). Please try again next month or contact support.",
        )

    daily_key = f"chat:user:{user.pk}:{now:%Y-%m-%d}"
    used = _bump(daily_key, timeout=2 * 86_400)
    if used > settings.CHAT_DAILY_USER_LIMIT:
        midnight = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            + timezone.timedelta(days=1)
        )
        reset = int(time.mktime(midnight.timetuple()))
        raise HttpError(
            429,
            f"Daily message limit reached "
            f"({settings.CHAT_DAILY_USER_LIMIT}/day). Resets at {reset} "
            f"(unix epoch). Reply tomorrow or upgrade your plan.",
        )


# ---------------------------------------------------------------------------
# Deterministic answer verification (Track B #1) + stale-use / abstain (PR4)
#
# After the model produces its answer, the shared gate in
# ``apps.corpus.services.answer`` re-scans it against the same corpus and checks,
# without LLM judgment: every section-shaped citation resolves to a live rule;
# every quoted passage appears in the rule it is attributed to; and (PR4) the
# answer did not silently rely on a case the retrieved context flags as
# negatively treated. Failures are surfaced as an explicit advisory (default),
# or — when ``RAG_ABSTAIN_BLOCKING`` is on — the answer is withheld. The two
# finalizers below are the chat-side adapters: they thread the turn's retrieved
# context into ``verify_answer`` / ``abstain_decision`` and emit the trace +
# stream events. The verification logic itself lives in ``answer.py`` so chat
# and any future answer surface share one checked path.
# ---------------------------------------------------------------------------


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    """The latest user turn — passed to ``verify_answer`` so quoted spans the
    answer echoes from the QUESTION (a hypothetical's "anywhere in North
    America") are not checked against source text."""
    return next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )


def _apply_verification(
    content: str,
    source_slug: str | None,
    trace: list["ToolCallTrace"],
    context: RetrievedContext | None = None,
    premise_problems: list[dict[str, Any]] | None = None,
    question: str = "",
) -> str:
    """Non-streaming finalizer: verify ``content`` against the corpus and the
    turn's retrieved ``context`` (PR4 stale-use), record the report on the trace
    for audit, then either append an advisory (default) or — when
    ``RAG_ABSTAIN_BLOCKING`` is on and the answer relied on invalidated authority
    / no good-law authority was retrieved — replace the answer with a
    withheld/abstain notice. ``context`` is ``None`` when the turn ran no search
    (lookup-only / pinned document), which suppresses the no-good-law block.
    ``premise_problems`` (PR6) are the pre-answer user-premise findings, folded
    into the report + advisory."""
    report = verify_answer(content, source_slug=source_slug, context=context,
                           premise_problems=premise_problems, question=question)
    if report is None:
        return content
    block, replacement = abstain_decision(
        report, context, searched=context is not None
    )
    report["blocked"] = block
    trace.append(
        ToolCallTrace(
            name="verify_answer",
            arguments={"source_slug": source_slug or ""},
            result=report,
        )
    )
    if block:
        return replacement
    return content + render_advisory(report)


def _finalize_stream(
    content: str,
    actual_model: str,
    source_slug: str | None,
    trace: list["ToolCallTrace"],
    context: RetrievedContext | None = None,
    premise_problems: list[dict[str, Any]] | None = None,
    question: str = "",
):
    """Streaming finalizer: emit the verification step events, then append the
    advisory (or block notice) as a trailing delta and close out with ``done``
    carrying the full content so the audit trace matches the UI.

    Note: the model's answer has already streamed to the user by the time this
    gate runs, so a hard *block* (``RAG_ABSTAIN_BLOCKING`` on) cannot un-send it
    here — it is surfaced as a prominent trailing notice, and the terminal
    ``done`` content carries that notice so the persisted/audited answer reflects
    it. True pre-emptive suppression on the streaming surface needs answer
    buffering (future work); the non-streaming path blocks outright."""
    report = verify_answer(content, source_slug=source_slug, context=context,
                           premise_problems=premise_problems, question=question)
    if report is None:
        yield ("done", content, actual_model)
        return

    block, replacement = abstain_decision(
        report, context, searched=context is not None
    )
    report["blocked"] = block

    yield ("verify_start",)
    trace.append(
        ToolCallTrace(
            name="verify_answer",
            arguments={"source_slug": source_slug or ""},
            result=report,
        )
    )
    if block:
        notice = "\n\n---\n\n" + replacement
        # Cannot retract already-streamed text; surface the block as a loud
        # trailing notice and carry it in the terminal content for the audit.
        yield ("delta", notice)
        yield ("verify_done", report)
        yield ("done", content + notice, actual_model)
        return
    advisory = render_advisory(report)
    if advisory:
        # Stream the advisory as visible answer text so the user sees the
        # warning inline, not just in the progress step.
        yield ("delta", advisory)
    yield ("verify_done", report)
    yield ("done", content + advisory, actual_model)


class ChatTurnError(Exception):
    """OpenAI / loop failure raised by ``run_chat_turn``.

    Carries the partial trace gathered before the failure so the caller can
    still log it (the view records it as an error row; the probe CLI prints
    what it had). The view re-raises this as a 502; other callers (e.g. the
    ``probe_chat`` management command) get the raw exception.
    """

    def __init__(self, message: str, *, trace: list[ToolCallTrace]):
        super().__init__(message)
        self.trace = trace
        # Messages are operator-authored (constants or exception type names —
        # never raw upstream error text), so the views may surface this to
        # the client. Kept as a separate field so that stays a deliberate
        # contract rather than an accident of str(exc).
        self.client_message = message


def run_chat_turn(
    *,
    messages: list[dict[str, Any]],
    source_slug: str | None,
    model: str,
    api_key: str,
    trace: list[ToolCallTrace] | None = None,
    node_id: int | None = None,
) -> tuple[str, str]:
    """Drive the OpenAI tool loop against the corpus tools.

    Returns ``(answer_content, actual_model_name)``. Mutates ``trace`` in
    place as each tool call resolves, so a caller passing its own list can
    inspect partial state even if we raise.

    Authentication, quota enforcement, ChatTrace persistence, and HTTP
    error translation are all the *caller's* job — the chat view layers
    them on top of this; the ``probe_chat`` CLI deliberately does not.
    Validation of ``model`` / ``messages`` is the caller's too, since the
    view returns 400 while the CLI prints to stderr.
    """
    if trace is None:
        trace = []

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ChatTurnError(
            "openai package is not installed on the server. "
            "Run `pip install -r requirements.txt` and restart.",
            trace=trace,
        ) from exc

    client = OpenAI(api_key=api_key)

    # Translate inbound messages into the OpenAI chat-completions format,
    # prepending our system prompt so each test request gets the same
    # grounding instructions.
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + _scope_preamble(source_slug)}
    ]
    pinned = _pinned_document(node_id)
    if pinned:
        convo.append({"role": "system", "content": pinned})
    for m in messages:
        role = m.get("role")
        if role not in {"user", "assistant", "system"}:
            raise ChatTurnError(f"unsupported role: {role}", trace=trace)
        convo.append({"role": role, "content": m.get("content", "")})

    token_state: dict = {}
    # PR4: keep every search_statutes context this turn so the final gate can
    # check the drafted answer against what was actually retrieved (stale-use)
    # and decide whether to abstain.
    search_contexts: list[RetrievedContext] = []
    # PR6: verify the user's case-holding premises before the model drafts, and
    # inject a caution so it corrects rather than anchors on a wrong premise.
    premise_caution, premise_problems = _premise_guard(messages, source_slug)
    if premise_caution:
        convo.append({"role": "system", "content": premise_caution})

    for i in range(MAX_TOOL_LOOPS):
        # Last round: stop offering tools and tell the model to synthesize
        # from what it has, so we never fall out of the loop empty-handed.
        final_round = i == MAX_TOOL_LOOPS - 1
        if final_round:
            convo.append({"role": "system", "content": SYNTHESIS_NUDGE})
        try:
            completion = _create_completion(
                client,
                {
                    "model": model,
                    "messages": convo,
                    "tools": OPENAI_TOOLS,
                    "tool_choice": "none" if final_round else "auto",
                    **_model_extras(model),
                },
                _token_budget(model),
                token_state,
            )
        except Exception as exc:
            # ChatTurnError text reaches the client (502 body / stream error
            # line), so carry only the exception type; the full message stays
            # in the server log.
            logger.exception("OpenAI call failed")
            raise ChatTurnError(
                f"OpenAI call failed: {type(exc).__name__}", trace=trace
            ) from exc

        # Token accounting: every round of the loop is real spend.
        emit_completion_usage(FEATURE_CHAT, completion, fallback_model=model)

        choice = completion.choices[0]
        msg = choice.message
        tool_calls = msg.tool_calls or []

        # No tools requested (normal exit), or the forced final round —
        # either way the model has produced its answer. Run the deterministic
        # verification gate over it before returning, so a fabricated citation
        # or misquote is flagged, not silently surfaced.
        if not tool_calls or final_round:
            content = _apply_verification(
                msg.content or "",
                source_slug,
                trace,
                context=_merge_turn_context(search_contexts),
                premise_problems=premise_problems,
                question=_last_user_message(messages),
            )
            return content, completion.model

        # Append the assistant turn (with its tool_calls) verbatim, then run
        # each tool and append the corresponding tool messages. The model
        # gets to react to the tool results on the next loop.
        convo.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            handler = TOOL_HANDLERS.get(tc.function.name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            # Scope is a user decision, not the model's: force the caller's
            # source_slug onto search and lookup so a Court Rule citation
            # resolves against the right corpus instead of silently missing.
            if (
                tc.function.name in ("search_statutes", "lookup_citation")
                and source_slug
            ):
                args["source_slug"] = source_slug
            if handler is None:
                result: dict[str, Any] = {
                    "error": f"unknown tool: {tc.function.name}"
                }
            elif tc.function.name == "search_statutes":
                # Capture the retrieved context (treatment flags + passages) so
                # the final gate can run stale-use / abstain against it.
                try:
                    result, ctx = _search_with_context(args)
                    if ctx is not None:
                        search_contexts.append(ctx)
                except Exception as exc:  # don't kill the loop on a bad arg
                    # Tool results are client-visible (trace in the response /
                    # done event), so expose the type only; detail to the log.
                    logger.exception("chat tool call failed")
                    result = {"error": f"tool call failed: {type(exc).__name__}"}
            else:
                try:
                    result = handler(args)
                except Exception as exc:  # don't kill the loop on a bad arg
                    # Tool results are client-visible (trace in the response /
                    # done event), so expose the type only; detail to the log.
                    logger.exception("chat tool call failed")
                    result = {"error": f"tool call failed: {type(exc).__name__}"}

            trace.append(
                ToolCallTrace(
                    name=tc.function.name,
                    arguments=args,
                    result=result,
                )
            )
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    # Unreachable: the final round always returns above. Kept as a defensive
    # best-effort so a logic change here can never regress to a hard 500 that
    # throws away an already-gathered trace.
    return (
        "I gathered sources but ran out of room to finish the analysis. "
        "Here is what I retrieved — please narrow the question and ask "
        "again for a complete answer.",
        model,
    )


def run_chat_turn_stream(
    *,
    messages: list[dict[str, Any]],
    source_slug: str | None,
    model: str,
    api_key: str,
    trace: list[ToolCallTrace] | None = None,
    node_id: int | None = None,
):
    """Generator variant of :func:`run_chat_turn`.

    Yields tuple events as the tool loop progresses:

    * ``("tool_start", name, args_dict)`` — emitted just before a tool runs
    * ``("delta", text)`` — a chunk of the model's visible answer
    * ``("done", full_content, actual_model)`` — terminal event with the
      assembled answer and the model id OpenAI actually billed

    Every round uses ``stream=True`` so visible text streams the moment the
    model starts emitting it — including from early rounds where the model
    decides not to call any more tools. Tool-call deltas (``id`` / ``name``
    / arguments JSON) arrive in pieces across chunks and are reassembled by
    index before the corresponding tool runs.

    Mutates ``trace`` in place exactly like :func:`run_chat_turn`. Raises
    :class:`ChatTurnError` carrying the partial trace on failure.
    """
    if trace is None:
        trace = []

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ChatTurnError(
            "openai package is not installed on the server. "
            "Run `pip install -r requirements.txt` and restart.",
            trace=trace,
        ) from exc

    client = OpenAI(api_key=api_key)

    convo: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + _scope_preamble(source_slug)}
    ]
    pinned = _pinned_document(node_id)
    if pinned:
        convo.append({"role": "system", "content": pinned})
    for m in messages:
        role = m.get("role")
        if role not in {"user", "assistant", "system"}:
            raise ChatTurnError(f"unsupported role: {role}", trace=trace)
        convo.append({"role": role, "content": m.get("content", "")})

    token_state: dict = {}
    # PR4: keep every search_statutes context this turn (see run_chat_turn).
    search_contexts: list[RetrievedContext] = []
    # PR6: pre-answer premise guard (see run_chat_turn).
    premise_caution, premise_problems = _premise_guard(messages, source_slug)
    if premise_caution:
        convo.append({"role": "system", "content": premise_caution})

    for i in range(MAX_TOOL_LOOPS):
        final_round = i == MAX_TOOL_LOOPS - 1
        if final_round:
            convo.append({"role": "system", "content": SYNTHESIS_NUDGE})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": convo,
            "tools": OPENAI_TOOLS,
            "tool_choice": "none" if final_round else "auto",
            "stream": True,
            # Token accounting: ask for a terminal usage chunk. Stripped and
            # retried by _create_completion if a proxy rejects the param.
            "stream_options": {"include_usage": True},
            **_model_extras(model),
        }

        try:
            stream = _create_completion(
                client, kwargs, _token_budget(model), token_state
            )
        except Exception as exc:
            # Client-visible (see run_chat_turn): type name only.
            logger.exception("OpenAI call failed")
            raise ChatTurnError(
                f"OpenAI call failed: {type(exc).__name__}", trace=trace
            ) from exc

        content_parts: list[str] = []
        # Tool calls arrive as deltas across chunks: each delta carries an
        # `index` plus partial id / name / arguments text. Reassemble per
        # index, then act once the stream finishes.
        tc_accum: dict[int, dict[str, Any]] = {}
        actual_model = model

        try:
            for chunk in stream:
                if getattr(chunk, "model", None):
                    actual_model = chunk.model
                # The include_usage terminal chunk carries usage with EMPTY
                # choices — read it before the empty-choices skip below.
                if getattr(chunk, "usage", None):
                    emit_completion_usage(
                        FEATURE_CHAT, chunk, fallback_model=actual_model
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                text = getattr(delta, "content", None)
                if text:
                    content_parts.append(text)
                    yield ("delta", text)

                for tcd in getattr(delta, "tool_calls", None) or []:
                    idx = tcd.index
                    slot = tc_accum.setdefault(
                        idx, {"id": None, "name": None, "args_text": ""}
                    )
                    if tcd.id:
                        slot["id"] = tcd.id
                    fn = getattr(tcd, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["args_text"] += fn.arguments

        except Exception as exc:
            # Client-visible (see run_chat_turn): type name only.
            logger.exception("OpenAI stream interrupted")
            raise ChatTurnError(
                f"OpenAI stream interrupted: {type(exc).__name__}", trace=trace
            ) from exc

        content = "".join(content_parts)
        tool_calls = [
            tc_accum[idx]
            for idx in sorted(tc_accum)
            if tc_accum[idx]["id"] and tc_accum[idx]["name"]
        ]

        # No tool calls — the model produced its final answer this round.
        # The visible text already streamed as deltas; now run the
        # deterministic verification gate (emitting its own progress events)
        # before closing out.
        if not tool_calls:
            yield from _finalize_stream(
                content,
                actual_model,
                source_slug,
                trace,
                context=_merge_turn_context(search_contexts),
                premise_problems=premise_problems,
                question=_last_user_message(messages),
            )
            return

        # Tool calls requested: record the assistant turn, run each tool,
        # append the tool messages, and loop. Any preface content that
        # arrived alongside the tool_calls is captured on the assistant
        # turn so the model can reference it next round if it likes.
        convo.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["args_text"] or "{}",
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            handler = TOOL_HANDLERS.get(tc["name"])
            try:
                args = json.loads(tc["args_text"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if (
                tc["name"] in ("search_statutes", "lookup_citation")
                and source_slug
            ):
                args["source_slug"] = source_slug

            yield ("tool_start", tc["name"], args)

            if handler is None:
                result: dict[str, Any] = {
                    "error": f"unknown tool: {tc['name']}"
                }
            elif tc["name"] == "search_statutes":
                # Capture the retrieved context for the final stale-use / abstain
                # gate (mirrors run_chat_turn).
                try:
                    result, ctx = _search_with_context(args)
                    if ctx is not None:
                        search_contexts.append(ctx)
                except Exception as exc:  # don't kill the loop on a bad arg
                    # Tool results are client-visible (trace in the response /
                    # done event), so expose the type only; detail to the log.
                    logger.exception("chat tool call failed")
                    result = {"error": f"tool call failed: {type(exc).__name__}"}
            else:
                try:
                    result = handler(args)
                except Exception as exc:  # don't kill the loop on a bad arg
                    # Tool results are client-visible (trace in the response /
                    # done event), so expose the type only; detail to the log.
                    logger.exception("chat tool call failed")
                    result = {"error": f"tool call failed: {type(exc).__name__}"}

            trace.append(
                ToolCallTrace(
                    name=tc["name"],
                    arguments=args,
                    result=result,
                )
            )
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, default=str),
                }
            )

    # Unreachable: the no-tool-calls branch always returns above, and the
    # forced final round (tool_choice="none") cannot emit tool_calls.
    # Defensive yield so a logic regression here can't drop the trace.
    yield (
        "done",
        "I gathered sources but ran out of room to finish the analysis. "
        "Here is what I retrieved — please narrow the question and ask "
        "again for a complete answer.",
        model,
    )


def _stream_ndjson_events(
    *, user, payload: "ChatRequest", api_key: str
):
    """Drive ``run_chat_turn_stream`` and serialize each event to an NDJSON
    line. After the generator completes (or fails), records the chat trace
    so the streamed turn shows up in the admin audit log just like the
    non-streaming endpoint."""
    trace: list[ToolCallTrace] = []
    started = time.monotonic()

    # Everything the turn spends — the tool-loop completions plus any
    # verification / rewrite side-calls they trigger — flushes as one
    # attributed LlmUsage turn when the generator finishes (numbers only;
    # the content-free counterpart of the unattributed trace below).
    with collect_usage(user):
        yield from _stream_ndjson_events_inner(
            user=user,
            payload=payload,
            api_key=api_key,
            trace=trace,
            started=started,
        )


def _stream_ndjson_events_inner(
    *, user, payload: "ChatRequest", api_key: str, trace, started
):
    content = ""
    actual_model = payload.model
    error: str | None = None

    try:
        gen = run_chat_turn_stream(
            messages=[
                {"role": m.role, "content": m.content} for m in payload.messages
            ],
            source_slug=payload.source_slug,
            model=payload.model,
            api_key=api_key,
            trace=trace,
            node_id=payload.node_id,
        )
        for event in gen:
            kind = event[0]
            if kind == "tool_start":
                line = {
                    "type": "tool_start",
                    "name": event[1],
                    "arguments": event[2],
                }
            elif kind == "verify_start":
                line = {"type": "verify_start"}
            elif kind == "verify_done":
                line = {"type": "verify_done", "report": event[1]}
            elif kind == "delta":
                line = {"type": "delta", "text": event[1]}
            elif kind == "done":
                content = event[1]
                actual_model = event[2]
                line = {
                    "type": "done",
                    "tool_calls": [
                        {
                            "name": t.name,
                            "arguments": t.arguments,
                            "result": t.result,
                        }
                        for t in trace
                    ],
                    "model": actual_model,
                }
            else:
                continue
            yield json.dumps(line, default=str) + "\n"
    except ChatTurnError as exc:
        error = exc.client_message
        # The generator owns the same `trace` list, so partial state is
        # already in `trace` by the time it raises — no need to copy.
        yield json.dumps({"type": "error", "message": error}) + "\n"
    except GeneratorExit:
        # Client disconnected mid-stream. Re-raise so Django can finalize
        # the response cleanly; the finally block still records the partial
        # trace below.
        error = "client disconnected"
        raise
    except Exception as exc:
        # Full detail goes to the server log and the ChatTrace error row
        # (via `error` in the finally block); the client only gets a generic
        # line so internals (paths, SQL, upstream error bodies) never cross
        # the wire.
        error = f"unexpected: {type(exc).__name__}: {exc}"
        logger.exception("chat stream failed")
        yield json.dumps(
            {"type": "error", "message": "unexpected server error"}
        ) + "\n"
    finally:
        record_chat_trace(
            user=user,
            payload=payload,
            content=content,
            trace=trace,
            model=actual_model,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=error,
        )


def _enforce_product_scope(request, user, payload: ChatRequest) -> None:
    """Server-side scope lock + entitlement gate for host-pinned products.

    ``request.product`` is set by ProductResolutionMiddleware from the Host. On a
    LOCKED product front door (e.g. ``clerk.<domain>`` -> the Ethics app) this:

      * requires the user to be ENTITLED to the product (else 403) — a client
        editing the request must not reach a scoped product they didn't pay for;
      * CLAMPS the corpus scope to the product's allowed sources so the request
        can't widen it. A single-source product is pinned to it; a multi-source
        product honours a client pick within the set;
      * drops a pinned ``node_id`` that lives outside the allowed sources, so a
        document can't be injected past the source filter.

    On the unlocked flagship app (no pinned product) it is a no-op and the
    client's scope is honoured. This is the ONE server-side authority point for
    scope; everything downstream keys off ``payload.source_slug`` / ``node_id``.
    """
    product = getattr(request, "product", None)
    if product is None:
        return

    if not is_entitled(user, product):
        raise HttpError(
            403,
            "Your account doesn't have access to this app. If it's provided by "
            "your bar association or firm, sign in with that account; otherwise "
            "contact support.",
        )

    allowed = product.allowed_source_slugs
    if not allowed:  # full-corpus product (e.g. a firm everything-license)
        return

    if payload.source_slug not in allowed:
        payload.source_slug = allowed[0]

    if payload.node_id is not None and not Node.objects.filter(
        id=payload.node_id, source__slug__in=allowed
    ).exists():
        payload.node_id = None


@chat_router.post("/chat/stream", auth=session_auth)
def chat_stream(request, payload: ChatRequest):
    """Streaming sibling of ``/api/chat``. Returns ``application/x-ndjson``;
    each line is one event (``tool_start`` / ``delta`` / ``done`` / ``error``).
    Same auth and quota gates as the non-streaming endpoint."""
    user = _require_login(request)
    require_paid_access(user)

    if not payload.messages:
        raise HttpError(400, "messages must not be empty")
    if payload.model not in ALLOWED_CHAT_MODELS:
        raise HttpError(400, f"unsupported model: {payload.model}")

    # Lock scope + check entitlement BEFORE any OpenAI work (host-pinned apps).
    _enforce_product_scope(request, user, payload)

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise HttpError(
            503,
            "The assistant is not configured (no server OpenAI key). "
            "Set OPENAI_API_KEY and restart.",
        )

    _enforce_chat_quota(user)

    response = StreamingHttpResponse(
        _stream_ndjson_events(user=user, payload=payload, api_key=api_key),
        content_type="application/x-ndjson",
    )
    response["Cache-Control"] = "no-cache"
    # nginx / Cloudflare honor X-Accel-Buffering: no to disable response
    # buffering. Belt-and-suspenders for any future proxy in front of us.
    response["X-Accel-Buffering"] = "no"
    return response


@chat_router.post("/chat", response={200: ChatResponse}, auth=session_auth)
def chat(request, payload: ChatRequest):
    # Login required: this endpoint spends our OpenAI key.
    user = _require_login(request)
    require_paid_access(user)

    if not payload.messages:
        raise HttpError(400, "messages must not be empty")
    if payload.model not in ALLOWED_CHAT_MODELS:
        raise HttpError(400, f"unsupported model: {payload.model}")

    # Lock scope + check entitlement BEFORE any OpenAI work (host-pinned apps).
    _enforce_product_scope(request, user, payload)

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise HttpError(
            503,
            "The assistant is not configured (no server OpenAI key). "
            "Set OPENAI_API_KEY and restart.",
        )

    # Gate spend BEFORE doing any OpenAI work.
    _enforce_chat_quota(user)

    trace: list[ToolCallTrace] = []
    started = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        # Attribute the turn's spend (tool-loop rounds + verification /
        # rewrite side-calls) to the user as one content-free LlmUsage turn.
        with collect_usage(user):
            content, actual_model = run_chat_turn(
                messages=[{"role": m.role, "content": m.content} for m in payload.messages],
                source_slug=payload.source_slug,
                model=payload.model,
                api_key=api_key,
                trace=trace,
                node_id=payload.node_id,
            )
    except ChatTurnError as exc:
        # A failed turn (and what it had retrieved before dying) is often
        # the most informative one to inspect, so capture the partial trace
        # before surfacing the error.
        record_chat_trace(
            user=user,
            payload=payload,
            content="",
            trace=exc.trace,
            model=payload.model,
            latency_ms=_elapsed_ms(),
            error=str(exc),
        )
        raise HttpError(502, exc.client_message) from exc

    record_chat_trace(
        user=user,
        payload=payload,
        content=content,
        trace=trace,
        model=actual_model,
        latency_ms=_elapsed_ms(),
    )
    return ChatResponse(content=content, tool_calls=trace, model=actual_model)
