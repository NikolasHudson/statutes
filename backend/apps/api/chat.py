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
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.api.accounts import _require_login
from apps.corpus.models import NodeVersion, Source
from apps.corpus.services.rerank import default_reranker
from apps.mcp_server.tools import (
    get_cross_references_tool,
    get_definitions_tool,
    get_section_at_date_tool,
    get_version_history_tool,
    list_recent_amendments_tool,
    lookup_citation_tool,
    search_statutes_tool,
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


def _excerpt(text: str, max_chars: int) -> str:
    """Trim ``text`` to ``max_chars``, breaking on a word boundary and
    flagging the cut with an ellipsis so the model (per the system prompt)
    knows to call lookup_citation for the complete section."""
    text = text.rstrip()
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    last_space = cut.rfind(" ")
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"

# Retrieve a wide candidate pool from hybrid search, then let the reranker
# pick the few that actually answer the question. Returning 18 loosely-related
# sections (the old behaviour) buried the on-point rule in noise; a tight,
# reranked set is what makes the answer — and its source list — trustworthy.
CHAT_CANDIDATE_POOL = 20
CHAT_DISPLAY_LIMIT = 6


def _enriched_search(args: dict) -> dict:
    """Wrap search_statutes_tool, then rerank the candidates against the
    query and keep only the most relevant few, each with a body excerpt long
    enough for the model to summarize.

    ``source_slug`` is injected by the chat endpoint from the request-level
    source picker, not chosen by the model — scoping is a user decision. The
    model's ``limit`` is intentionally ignored: chat noise is a precision
    problem, not a recall one."""
    result = search_statutes_tool(
        args["query"],
        limit=CHAT_CANDIDATE_POOL,
        use_vector=args.get("use_vector", True),
        source_slug=args.get("source_slug"),
    )
    hits = result.get("hits") or []
    if not hits:
        return result

    node_ids = [h["node"]["id"] for h in hits]
    # Get the current body for each node (effective_to IS NULL).
    bodies: dict[int, str] = {}
    for nv in NodeVersion.objects.filter(
        node_id__in=node_ids, effective_to__isnull=True
    ).only("node_id", "body_text"):
        bodies.setdefault(nv.node_id, nv.body_text)

    # Rerank on heading + body so the cross-encoder sees what the section is
    # actually about, not just its first sentence.
    by_node = {h["node"]["id"]: h for h in hits}
    candidates: list[tuple[int, str]] = [
        (
            nid,
            f"{by_node[nid]['node'].get('heading', '')}\n"
            f"{bodies.get(nid, by_node[nid].get('snippet', ''))}",
        )
        for nid in node_ids
    ]
    ranked_ids = default_reranker().rerank(
        args["query"], candidates, top_k=CHAT_DISPLAY_LIMIT
    )

    ordered: list[dict] = []
    for rank, nid in enumerate(ranked_ids):
        h = by_node[nid]
        budget = (
            SEARCH_BODY_MAX_CHARS_TOP
            if rank < TOP_HITS_FULL
            else SEARCH_BODY_MAX_CHARS
        )
        h["body_excerpt"] = _excerpt(bodies.get(nid, ""), budget)
        ordered.append(h)

    result["hits"] = ordered
    return result


chat_router = Router()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatMessage(Schema):
    role: str  # "user" | "assistant" | "system"
    content: str


# Models a logged-in user is allowed to spend our key on. Keeping this tight
# is a cost control: an unrestricted `model` field would let any session pick
# the most expensive model. Add to this set deliberately, not by request.
ALLOWED_CHAT_MODELS = {"gpt-4o-mini", "gpt-4o"}
DEFAULT_CHAT_MODEL = "gpt-4o-mini"


class ChatRequest(Schema):
    messages: list[ChatMessage]
    model: str = DEFAULT_CHAT_MODEL
    # Optional corpus scope (e.g. "iowa-court-rules"). None searches all
    # sources. Forced into every search_statutes call; the model cannot
    # override it.
    source_slug: str | None = None


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
    "applies.\n\n"
    "Your answer must summarize what the statute actually says — list the "
    "requirements, conditions, exceptions, deadlines, etc. Do NOT just hand "
    "the user a citation and a link; that is unhelpful. Quote short phrases "
    "where they're load-bearing.\n\n"
    "GROUNDING RULES — these are absolute:\n"
    "• Never state a rule/section number, deadline, day-count, dollar amount, "
    "or any other specific that does not appear verbatim in a tool result. "
    "Words like 'typically', 'often', 'usually', or 'such as 10 days' before "
    "a specific are a sign you are guessing — stop and call a tool instead.\n"
    "• Do not claim a rule 'governs' or 'also governs' a sub-question unless "
    "that rule's own retrieved text actually addresses it. Stretching the "
    "initial-response rule to cover a post-ruling deadline it never mentions "
    "is a hallucination.\n"
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
    "substitute a remembered rule number.\n\n"
    "Always include the official URL and the effective_from date from the "
    "tool output. If a citation is ambiguous, present the candidates and "
    "ask the user to pick — never silently substitute.\n\n"
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


@chat_router.post("/chat", response={200: ChatResponse}, auth=None)
def chat(request, payload: ChatRequest):
    # Login required: this endpoint spends our OpenAI key.
    user = _require_login(request)

    if not payload.messages:
        raise HttpError(400, "messages must not be empty")
    if payload.model not in ALLOWED_CHAT_MODELS:
        raise HttpError(400, f"unsupported model: {payload.model}")

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise HttpError(
            503,
            "The assistant is not configured (no server OpenAI key). "
            "Set OPENAI_API_KEY and restart.",
        )

    # Gate spend BEFORE doing any OpenAI work.
    _enforce_chat_quota(user)

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HttpError(
            500,
            "openai package is not installed on the server. "
            "Run `pip install -r requirements.txt` and restart.",
        ) from exc

    client = OpenAI(api_key=api_key)

    # Translate request messages into the OpenAI chat-completions format,
    # prepending our system prompt so each test request gets the same
    # grounding instructions.
    convo: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + _scope_preamble(payload.source_slug)}
    ]
    for m in payload.messages:
        if m.role not in {"user", "assistant", "system"}:
            raise HttpError(400, f"unsupported role: {m.role}")
        convo.append({"role": m.role, "content": m.content})

    trace: list[ToolCallTrace] = []
    token_state: dict = {}

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
                    "model": payload.model,
                    "messages": convo,
                    "tools": OPENAI_TOOLS,
                    "tool_choice": "none" if final_round else "auto",
                },
                ANSWER_MAX_TOKENS,
                token_state,
            )
        except Exception as exc:
            # OpenAI auth/quota/etc. — surface a 502 with the message so the
            # test page can show what went wrong.
            raise HttpError(502, f"OpenAI call failed: {exc}") from exc

        choice = completion.choices[0]
        msg = choice.message
        tool_calls = msg.tool_calls or []

        # No tools requested (normal exit), or the forced final round —
        # either way the model has produced its answer; return it with the
        # full trace so the UI can still render verifiable source cards.
        if not tool_calls or final_round:
            return ChatResponse(
                content=msg.content or "",
                tool_calls=trace,
                model=completion.model,
            )

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
            # Scope is a user decision, not the model's: force the request's
            # source_slug onto search and lookup so a Court Rule citation
            # resolves against the right corpus instead of silently missing.
            if (
                tc.function.name in ("search_statutes", "lookup_citation")
                and payload.source_slug
            ):
                args["source_slug"] = payload.source_slug
            if handler is None:
                result: dict[str, Any] = {
                    "error": f"unknown tool: {tc.function.name}"
                }
            else:
                try:
                    result = handler(args)
                except Exception as exc:  # don't kill the loop on a bad arg
                    result = {"error": f"{type(exc).__name__}: {exc}"}

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
    return ChatResponse(
        content=(
            "I gathered sources but ran out of room to finish the analysis. "
            "Here is what I retrieved — please narrow the question and ask "
            "again for a complete answer."
        ),
        tool_calls=trace,
        model=payload.model,
    )
