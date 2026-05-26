"""Drive the chat tool loop from the CLI for search-quality inspection.

The /api/chat endpoint runs an OpenAI tool-calling loop against the corpus
tools and returns a final answer plus a trace of every tool call. This
command runs the *same* loop (same prompt, same enrichment, same
scope-forcing) outside HTTP — no login, no quota, no ChatTrace write — and
prints a diagnostic that makes "is the assistant calling the best
information?" easy to read.

Usage:

    # One question, scoped to the Iowa Court Rules.
    python manage.py probe_chat "deadline to answer a counterclaim"

    # Custom corpus.
    python manage.py probe_chat "consumer fraud" --source iowa-code

    # Batch from the seed JSON (apps/api/data/chat_eval_court_rules.json).
    python manage.py probe_chat --queries apps/api/data/chat_eval_court_rules.json

    # Machine-readable.
    python manage.py probe_chat "q..." --json

The pretty-printer shows, for each tool call, the arguments the model
passed and a compact view of the result — for ``search_statutes``, the
reranked top hits with their rank, citation, heading, and chapter, with a
★ next to any hit the final answer actually cited (same ``_answer_uses``
heuristic the admin trace view uses). When the eval entry includes
``expected_paths``, the script also reports hit@K (was the expected path
in the retrieved set?) and cited@K (did the answer actually cite it?).

Spends OpenAI credit on every run — that is the point: we want to see what
the *real* tool loop, with the *real* reranker, does end-to-end.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.api.chat import (
    ALLOWED_CHAT_MODELS,
    DEFAULT_CHAT_MODEL,
    ChatTurnError,
    ToolCallTrace,
    run_chat_turn,
)
from apps.api.trace_capture import _answer_uses
from apps.corpus.models import Node, Source


DEFAULT_SOURCE_SLUG = "iowa-court-rules"


DEFAULT_KIND = "search_substantive"
# Out-of-scope questions can't be scored against expected_paths (there are
# none); the metric is abstention — did the answer avoid citing any specific
# Court Rule? An out-of-scope outcome "passes" when no path appears in the
# answer's citation list.
OUT_OF_SCOPE_KIND = "out_of_scope"


@dataclass
class TurnOutcome:
    """Everything one probed question produced — answer, trace, latency,
    and (when ``expected_paths`` was supplied) the per-question scoring
    that drives the summary."""

    question: str
    kind: str
    answer: str
    model: str
    trace: list[dict[str, Any]]
    latency_ms: int
    error: str | None
    # Eval scoring (None when expected_paths wasn't supplied AND kind isn't
    # out_of_scope).
    expected_paths: list[str] | None
    expected_in_corpus: list[str] | None
    retrieved_paths: list[str] | None  # union across every search/lookup call
    cited_paths: list[str] | None
    retrieval_hit: bool | None
    cite_hit: bool | None
    # For out_of_scope: True if the answer abstained from citing any rule
    # (the right behaviour), False if it cited something.
    abstained: bool | None


class Command(BaseCommand):
    help = (
        "Probe the chat tool loop end-to-end. Prints what the model "
        "searched, what the corpus returned, and which hits the answer "
        "actually cited."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "question",
            nargs="?",
            help=(
                "A single natural-language question. Omit when using "
                "--queries for batch mode."
            ),
        )
        parser.add_argument(
            "--queries",
            type=str,
            help=(
                "Path to a JSON eval file (see "
                "apps/api/data/chat_eval_court_rules.json for the shape). "
                "Each entry: {question, expected_paths?, tags?}."
            ),
        )
        parser.add_argument(
            "--source",
            type=str,
            default=DEFAULT_SOURCE_SLUG,
            help=(
                "Source slug to scope the chat to "
                "(default: iowa-court-rules). Pass an empty string to "
                "search every loaded source."
            ),
        )
        parser.add_argument(
            "--model",
            type=str,
            default=DEFAULT_CHAT_MODEL,
            help=(
                f"OpenAI model (default: {DEFAULT_CHAT_MODEL}). Must be one "
                f"of: {', '.join(sorted(ALLOWED_CHAT_MODELS))}."
            ),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON to stdout instead of the human-readable trace.",
        )

    # ------------------------------------------------------------------
    # Entrypoint
    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        question = (opts.get("question") or "").strip()
        queries_path = opts.get("queries")
        if not question and not queries_path:
            raise CommandError(
                "Provide a question (positional) OR --queries path."
            )
        if question and queries_path:
            raise CommandError(
                "Pass either a question or --queries, not both."
            )

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise CommandError(
                "OPENAI_API_KEY is not set. Export it in your env "
                "(this command really does call OpenAI)."
            )

        model = opts["model"]
        if model not in ALLOWED_CHAT_MODELS:
            raise CommandError(
                f"unsupported model: {model!r}. "
                f"Allowed: {sorted(ALLOWED_CHAT_MODELS)}."
            )

        source_slug: str | None = opts["source"] or None
        if source_slug and not Source.objects.filter(slug=source_slug).exists():
            raise CommandError(
                f"no Source with slug={source_slug!r} is loaded. "
                f"Loaded slugs: "
                f"{sorted(Source.objects.values_list('slug', flat=True).distinct())}."
            )

        # Build the list of (question, expected_paths, tags) tuples.
        entries: list[dict[str, Any]] = []
        if queries_path:
            entries = self._load_queries(Path(queries_path))
        else:
            entries = [
                {
                    "question": question,
                    "expected_paths": [],
                    "tags": [],
                    "kind": DEFAULT_KIND,
                }
            ]

        # Skip entries whose expected paths are not loaded in the corpus —
        # an empty corpus would otherwise tank the score. Echoes
        # eval_search's behaviour so the two commands stay legible together.
        loaded_paths = set(
            Node.objects.filter(source__slug=source_slug).values_list(
                "path", flat=True
            )
            if source_slug
            else Node.objects.values_list("path", flat=True)
        )

        outcomes: list[TurnOutcome] = []
        for entry in entries:
            outcomes.append(
                self._probe_one(
                    entry=entry,
                    source_slug=source_slug,
                    model=model,
                    api_key=api_key,
                    loaded_paths=loaded_paths,
                )
            )

        if opts["json"]:
            self._emit_json(outcomes, source_slug=source_slug, model=model)
        else:
            for o in outcomes:
                self._render_outcome(o, source_slug=source_slug)
            if len(outcomes) > 1:
                self._render_summary(outcomes)

    # ------------------------------------------------------------------
    # Loading + probing
    # ------------------------------------------------------------------

    def _load_queries(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise CommandError(f"queries file not found: {path}")
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise CommandError(f"invalid JSON in {path}: {e}") from e
        raw = payload.get("queries")
        if not isinstance(raw, list) or not raw:
            raise CommandError("queries file must have a non-empty 'queries' list")
        out: list[dict[str, Any]] = []
        for i, entry in enumerate(raw):
            q = (entry.get("question") or "").strip()
            if not q:
                raise CommandError(f"entry {i} has no 'question'")
            out.append(
                {
                    "question": q,
                    "expected_paths": list(entry.get("expected_paths") or []),
                    "tags": list(entry.get("tags") or []),
                    "kind": entry.get("kind") or DEFAULT_KIND,
                }
            )
        return out

    def _probe_one(
        self,
        *,
        entry: dict[str, Any],
        source_slug: str | None,
        model: str,
        api_key: str,
        loaded_paths: set[str],
    ) -> TurnOutcome:
        question = entry["question"]
        kind = entry.get("kind") or DEFAULT_KIND
        expected_paths = entry["expected_paths"]
        trace_objs: list[ToolCallTrace] = []
        started = time.monotonic()
        content = ""
        actual_model = model
        error: str | None = None
        try:
            content, actual_model = run_chat_turn(
                messages=[{"role": "user", "content": question}],
                source_slug=source_slug,
                model=model,
                api_key=api_key,
                trace=trace_objs,
            )
        except ChatTurnError as exc:
            # Use whatever trace was gathered before the failure — that is
            # often the most informative part of the run.
            trace_objs = exc.trace
            error = str(exc)
        latency_ms = int((time.monotonic() - started) * 1000)
        trace = _trace_to_dicts(trace_objs)

        retrieved_paths = _all_retrieved_paths(trace)
        cited_paths = sorted(p for p in retrieved_paths if p and p in content)
        abstained: bool | None = None
        if expected_paths:
            expected_in_corpus = sorted(set(expected_paths) & loaded_paths)
            if expected_in_corpus:
                retrieval_hit = bool(set(expected_in_corpus) & set(retrieved_paths))
                cite_hit = bool(set(expected_in_corpus) & set(cited_paths))
            else:
                retrieval_hit = None
                cite_hit = None
        elif kind == OUT_OF_SCOPE_KIND:
            # Pass condition: the answer cited NO Court Rule path. Anything
            # the model dragged into context but didn't cite is fine — what
            # matters is whether the user sees a fabricated authority.
            expected_in_corpus = []
            retrieval_hit = None
            cite_hit = None
            abstained = not cited_paths
        else:
            expected_in_corpus = None
            retrieval_hit = None
            cite_hit = None

        return TurnOutcome(
            question=question,
            kind=kind,
            answer=content,
            model=actual_model,
            trace=trace,
            latency_ms=latency_ms,
            error=error,
            expected_paths=expected_paths or None,
            expected_in_corpus=expected_in_corpus,
            retrieved_paths=retrieved_paths,
            cited_paths=cited_paths,
            retrieval_hit=retrieval_hit,
            cite_hit=cite_hit,
            abstained=abstained,
        )

    # ------------------------------------------------------------------
    # Pretty output
    # ------------------------------------------------------------------

    def _render_outcome(self, o: TurnOutcome, *, source_slug: str | None) -> None:
        bar = "=" * 78
        self.stdout.write("")
        self.stdout.write(bar)
        self.stdout.write(self.style.MIGRATE_HEADING(f"Q [{o.kind}]: {o.question}"))
        self.stdout.write(
            f"   source={source_slug or '<all>'}  model={o.model}  "
            f"latency={o.latency_ms}ms  tool_calls={len(o.trace)}"
        )

        if not o.trace:
            self.stdout.write(self.style.WARNING("\n  (no tool calls)"))
        else:
            self.stdout.write("")
            for n, call in enumerate(o.trace, 1):
                self._render_call(n, call, o.answer)

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Answer:"))
        if o.error:
            self.stdout.write(self.style.ERROR(f"  ERROR: {o.error}"))
        if o.answer:
            for line in o.answer.splitlines() or [o.answer]:
                self.stdout.write(f"  {line}")
        elif not o.error:
            self.stdout.write(self.style.WARNING("  (empty)"))

        if o.expected_paths:
            self.stdout.write("")
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"Relevance vs expected_paths={o.expected_paths!r}:"
                )
            )
            missing = sorted(set(o.expected_paths) - set(o.expected_in_corpus or []))
            if missing:
                self.stdout.write(
                    self.style.WARNING(
                        f"  expected paths NOT in loaded corpus: {missing} "
                        "(skipped from scoring)"
                    )
                )
            if o.expected_in_corpus:
                hit_word = (
                    self.style.SUCCESS("HIT ")
                    if o.retrieval_hit
                    else self.style.ERROR("MISS")
                )
                cite_word = (
                    self.style.SUCCESS("YES ")
                    if o.cite_hit
                    else self.style.ERROR("NO  ")
                )
                self.stdout.write(
                    f"  retrieval: {hit_word}  retrieved={o.retrieved_paths or []}"
                )
                self.stdout.write(
                    f"  answer cites expected: {cite_word}  "
                    f"cited={o.cited_paths or []}"
                )
        elif o.kind == OUT_OF_SCOPE_KIND:
            self.stdout.write("")
            self.stdout.write(self.style.HTTP_INFO("Abstention check (out-of-scope):"))
            word = (
                self.style.SUCCESS("ABSTAINED")
                if o.abstained
                else self.style.ERROR("CITED ANYWAY")
            )
            self.stdout.write(
                f"  {word}  cited={o.cited_paths or []}"
            )

    def _render_call(self, n: int, call: dict, answer: str) -> None:
        name = call.get("name", "?")
        args = call.get("arguments") or {}
        result = call.get("result") or {}
        header = self.style.HTTP_INFO(f"  [{n}] {name}")
        # Show args compactly — drop noisy/forced fields the chat layer injected.
        display_args = {
            k: v
            for k, v in args.items()
            if k not in ("source_slug",) and v not in (None, "")
        }
        self.stdout.write(f"{header}  args={json.dumps(display_args, default=str)}")

        if "error" in result:
            self.stdout.write(self.style.ERROR(f"      → error: {result['error']}"))

        if name == "search_statutes":
            self._render_search(result, answer)
        elif name == "lookup_citation":
            self._render_lookup(result)
        elif name == "get_definitions":
            defs = result.get("definitions") or []
            self.stdout.write(f"      → {len(defs)} definition(s)")
            for d in defs[:3]:
                node = d.get("node") or {}
                self.stdout.write(
                    f"        - {node.get('citation') or node.get('path')}: "
                    f"{(d.get('definition') or '')[:120]}"
                )
        elif name == "get_cross_references":
            refs = result.get("references") or []
            self.stdout.write(f"      → {len(refs)} cross-reference(s)")
        elif name == "list_recent_amendments":
            rows = result.get("amendments") or []
            self.stdout.write(f"      → {len(rows)} amendment(s) since {result.get('since')}")
        elif name in ("get_version_history", "get_section_at_date"):
            node = result.get("node") or {}
            self.stdout.write(
                f"      → {node.get('citation') or node.get('path') or '?'}"
            )

    def _render_search(self, result: dict, answer: str) -> None:
        hits = result.get("hits") or []
        if not hits:
            self.stdout.write(self.style.WARNING("      → 0 hits"))
            return
        self.stdout.write(
            f"      → {len(hits)} reranked hit(s) "
            f"(★ = path/citation appears in the final answer)"
        )
        for rank, h in enumerate(hits):
            node = h.get("node") if isinstance(h, dict) else None
            node = node if isinstance(node, dict) else {}
            star = "★" if _answer_uses(answer, h if isinstance(h, dict) else {}) else " "
            chapter = node.get("chapter") or {}
            chap_str = (
                f"  [ch {chapter.get('ordinal') or '?'}]" if chapter else ""
            )
            heading = (node.get("heading") or "").strip()
            cite = node.get("citation") or node.get("path") or "?"
            self.stdout.write(
                f"        {star} {rank:2d}. {cite:32s} {heading[:60]}{chap_str}"
            )

    def _render_lookup(self, result: dict) -> None:
        if result.get("parse_error"):
            self.stdout.write(
                self.style.ERROR(f"      → parse_error: {result['parse_error']}")
            )
            return
        if not result.get("found"):
            cands = result.get("candidates") or []
            self.stdout.write(
                self.style.WARNING(
                    f"      → NOT FOUND, {len(cands)} same-chapter candidate(s)"
                )
            )
            for c in cands[:5]:
                self.stdout.write(
                    f"        - {c.get('citation') or c.get('path')}: "
                    f"{(c.get('heading') or '')[:60]}"
                )
            return
        section = result.get("section")
        chapter = result.get("chapter")
        if section:
            node = section.get("node") or {}
            version = section.get("version") or {}
            body = version.get("body_text") or ""
            self.stdout.write(
                f"      → found {node.get('citation') or node.get('path')}  "
                f"effective_from={version.get('effective_from')}  "
                f"body={len(body)} chars"
            )
        elif chapter:
            node = chapter.get("node") or {}
            secs = chapter.get("sections") or []
            self.stdout.write(
                f"      → chapter hit {node.get('citation') or node.get('path')} "
                f"({len(secs)} section(s))"
            )

    def _render_summary(self, outcomes: list[TurnOutcome]) -> None:
        scorable = [o for o in outcomes if o.retrieval_hit is not None]
        oos = [o for o in outcomes if o.abstained is not None]
        if not scorable and not oos:
            return
        bar = "=" * 78
        self.stdout.write("")
        self.stdout.write(bar)
        self.stdout.write(self.style.MIGRATE_HEADING("Eval summary"))

        if scorable:
            n = len(scorable)
            ret_hits = sum(1 for o in scorable if o.retrieval_hit)
            cite_hits = sum(1 for o in scorable if o.cite_hit)
            self.stdout.write(f"  scored:                       {n}/{len(outcomes)}")
            self.stdout.write(
                f"  retrieval hit (expected in hits): {ret_hits}/{n} "
                f"({ret_hits / n:.0%})"
            )
            self.stdout.write(
                f"  answer cites expected:            {cite_hits}/{n} "
                f"({cite_hits / n:.0%})"
            )

        if oos:
            abst = sum(1 for o in oos if o.abstained)
            self.stdout.write("")
            self.stdout.write(
                f"  out-of-scope abstentions:         {abst}/{len(oos)} "
                f"({abst / len(oos):.0%})"
            )

        # Per-kind breakdown — useful for spotting "scenarios are weak even
        # though lookups are 100%" without re-reading every block.
        by_kind: dict[str, list[TurnOutcome]] = {}
        for o in outcomes:
            by_kind.setdefault(o.kind, []).append(o)
        if len(by_kind) > 1:
            self.stdout.write("")
            self.stdout.write("  by kind:")
            for kind in sorted(by_kind):
                rows = by_kind[kind]
                rk = [r for r in rows if r.retrieval_hit is not None]
                ok = [r for r in rows if r.abstained is not None]
                parts: list[str] = []
                if rk:
                    rh = sum(1 for r in rk if r.retrieval_hit)
                    ch = sum(1 for r in rk if r.cite_hit)
                    parts.append(f"hit@K={rh}/{len(rk)}  cited={ch}/{len(rk)}")
                if ok:
                    ab = sum(1 for r in ok if r.abstained)
                    parts.append(f"abstain={ab}/{len(ok)}")
                if not parts:
                    parts.append(f"n={len(rows)} (unscored)")
                self.stdout.write(
                    f"    {kind:20s} n={len(rows):3d}  {'  '.join(parts)}"
                )

        errored = [o for o in outcomes if o.error]
        if errored:
            self.stdout.write(
                self.style.ERROR(f"\n  {len(errored)} run(s) errored:")
            )
            for o in errored:
                self.stdout.write(f"    - {o.question[:60]}: {o.error}")

    def _emit_json(
        self,
        outcomes: list[TurnOutcome],
        *,
        source_slug: str | None,
        model: str,
    ) -> None:
        payload = {
            "source_slug": source_slug,
            "model": model,
            "outcomes": [
                {
                    "question": o.question,
                    "kind": o.kind,
                    "answer": o.answer,
                    "model": o.model,
                    "latency_ms": o.latency_ms,
                    "error": o.error,
                    "expected_paths": o.expected_paths,
                    "expected_in_corpus": o.expected_in_corpus,
                    "retrieved_paths": o.retrieved_paths,
                    "cited_paths": o.cited_paths,
                    "retrieval_hit": o.retrieval_hit,
                    "cite_hit": o.cite_hit,
                    "abstained": o.abstained,
                    "tool_calls": o.trace,
                }
                for o in outcomes
            ],
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trace_to_dicts(trace: list[ToolCallTrace]) -> list[dict[str, Any]]:
    """Normalize ninja Schema objects into plain dicts so the rest of the
    command can treat the trace as raw JSON regardless of pydantic version."""
    out: list[dict[str, Any]] = []
    for tc in trace:
        if isinstance(tc, dict):
            out.append(tc)
            continue
        out.append(
            {
                "name": getattr(tc, "name", ""),
                "arguments": dict(getattr(tc, "arguments", {}) or {}),
                "result": dict(getattr(tc, "result", {}) or {}),
            }
        )
    return out


def _all_retrieved_paths(trace: list[dict[str, Any]]) -> list[str]:
    """Every node.path the model successfully pulled into context this turn,
    ordered by first appearance — search hits AND direct citation lookups.

    Without the lookup_citation branch, a turn that goes straight to
    ``lookup_citation('1.904')`` would score MISS even though the expected
    rule was found and cited; the model just used the more direct tool."""
    seen: list[str] = []
    seen_set: set[str] = set()

    def _add(path: str | None) -> None:
        if path and path not in seen_set:
            seen.append(path)
            seen_set.add(path)

    for call in trace:
        name = call.get("name")
        result = call.get("result") or {}
        if name == "search_statutes":
            for h in result.get("hits") or []:
                node = h.get("node") if isinstance(h, dict) else None
                _add((node or {}).get("path") if isinstance(node, dict) else None)
        elif name == "lookup_citation":
            section = result.get("section")
            chapter = result.get("chapter")
            if section and isinstance(section.get("node"), dict):
                _add(section["node"].get("path"))
            elif chapter and isinstance(chapter.get("node"), dict):
                _add(chapter["node"].get("path"))
                for n in chapter.get("sections") or []:
                    if isinstance(n, dict):
                        _add(n.get("path"))
    return seen
