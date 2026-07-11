"""LLM-as-judge for caselaw retrieval quality (eval-only).

The rank metrics in ``eval_caselaw`` ask one question: "is the single pre-labeled
ground-truth case at rank 1?" That structurally cannot tell us the thing we
actually care about for question-answering — *can a correct answer be produced
from what was retrieved?* A target at rank 3 behind two on-point cases is a good
result the rank metric records as a near-miss; conversely a top-5 full of
*relevant but overruled* cases (e.g. Godfrey after Burnett killed it) scores fine
on rank yet would lead a RAG answer straight into superseded law.

This judge closes that gap. Given the user's QUESTION and the top-K retrieved
cases (name, citation, date, opinion excerpt), one OpenAI call:
  1. ANSWERS the question grounded in the supplied cases (so we can read what a
     RAG layer would actually say), and
  2. grades the retrieval — answerable yes/partial/no, the best case, per-case
     relevance, whether the current *controlling* authority is present, and a
     stale_warning when a surfaced case is known to be overruled/superseded.

Mirrors ``semantic_support.OpenAIChecker``: same ``settings.OPENAI_API_KEY``,
JSON mode, and gpt-5/o-series reasoning-tier handling. ``default_judge()``
returns ``None`` when no key is set so the eval simply skips the judge pass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings

log = logging.getLogger(__name__)

# gpt-4o, not -mini: the judge needs sound legal reasoning AND recall of which
# landmark cases have been overruled (the stale_warning). semantic_support's
# comment records that gpt-4o-mini proved too weak on nuanced legal reasoning.
_DEFAULT_MODEL = "gpt-4o"
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

_ANSWERABLE = {"yes", "partial", "no"}
_RELEVANCE = {"high", "medium", "low", "off"}


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


SYSTEM_PROMPT = (
    "You are a meticulous Iowa legal research assistant evaluating a case-law "
    "retrieval system. You receive a user's legal QUESTION and the TOP retrieved "
    "cases in rank order — each with its name, citation, decision date, and an "
    "excerpt from the opinion. Do BOTH of the following.\n"
    "\n"
    "PART 1 — ANSWER. In 2-4 sentences, answer the question grounded ONLY in the "
    "supplied cases, naming the case(s) you rely on. If the supplied cases are "
    "insufficient to answer, say so plainly rather than inventing law.\n"
    "\n"
    "PART 2 — GRADE the retrieval:\n"
    '  - "answerable": "yes" if a correct, well-grounded answer to the question '
    'can be given from these cases; "partial" if only a hedged or incomplete '
    'answer is possible; "no" if the cases do not support an answer.\n'
    '  - "best_case": the single supplied case that most directly answers the '
    "question (use its name as given).\n"
    '  - "per_case": for EVERY supplied case, its relevance to the question — '
    '"high" (directly on point / dispositive), "medium" (related, useful '
    'context), "low" (same general area only), or "off" (not relevant).\n'
    '  - "controlling_present": true if the CURRENT controlling authority on '
    "this question appears to be among the supplied cases, otherwise false.\n"
    '  - "stale_warning": this is the ONE place you may use outside knowledge — '
    "if you know that any supplied case has been OVERRULED, SUPERSEDED, or "
    "abrogated, name it and the case that did so (e.g. \"Godfrey v. State was "
    "overruled by Burnett v. Smith (2023)\"). If a higher-ranked case is stale "
    "and a lower-ranked supplied case is the live law, say that. Empty string "
    "if nothing is stale.\n"
    '  - "rationale": one or two sentences on the retrieval quality.\n'
    "\n"
    "Respond with ONLY a JSON object of the form: "
    '{"answer": "...", "answerable": "yes|partial|no", "best_case": "...", '
    '"controlling_present": true|false, "stale_warning": "...", '
    '"per_case": [{"case": "...", "relevance": "high|medium|low|off"}], '
    '"rationale": "..."}'
)


@dataclass
class JudgeVerdict:
    answer: str = ""
    answerable: str = "no"  # yes | partial | no
    best_case: str = ""
    controlling_present: bool = False
    stale_warning: str = ""
    per_case: list = field(default_factory=list)  # [{"case","relevance"}]
    rationale: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "answerable": self.answerable,
            "best_case": self.best_case,
            "controlling_present": self.controlling_present,
            "stale_warning": self.stale_warning,
            "per_case": self.per_case,
            "rationale": self.rationale,
            "error": self.error,
        }


class RetrievalJudge(Protocol):
    def judge(self, query: str, cases: list[dict]) -> JudgeVerdict:
        ...


def _format_cases(cases: list[dict]) -> str:
    """Render the retrieved cases as a numbered, rank-ordered block."""
    parts = []
    for c in cases:
        head = f"#{c.get('rank')} {c.get('case_name', '?')}"
        meta = " | ".join(
            x for x in (c.get("citation"), c.get("date")) if x
        )
        if meta:
            head += f"  ({meta})"
        parts.append(f"{head}\nEXCERPT: {c.get('excerpt', '').strip()}")
    return "\n\n".join(parts)


@dataclass
class OpenAIRetrievalJudge:
    model: str = _DEFAULT_MODEL
    api_key: str | None = None
    max_tokens: int = 900

    def _key(self) -> str:
        return self.api_key or getattr(settings, "OPENAI_API_KEY", "")

    def judge(self, query: str, cases: list[dict]) -> JudgeVerdict:
        key = self._key()
        if not key:
            return JudgeVerdict(error="no OPENAI_API_KEY")
        if not cases:
            return JudgeVerdict(answerable="no", error="no cases retrieved")
        try:
            from openai import OpenAI
        except ImportError:
            return JudgeVerdict(error="openai SDK not installed")

        user = (
            f"QUESTION:\n{query}\n\n"
            f"TOP {len(cases)} RETRIEVED CASES:\n{_format_cases(cases)}"
        )
        kwargs: dict = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        if _is_reasoning_model(self.model):
            kwargs["max_completion_tokens"] = max(self.max_tokens, 4000)
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["max_tokens"] = self.max_tokens
            kwargs["temperature"] = 0
        try:
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(**kwargs)
            # Token accounting (lazy import — see semantic_support for why).
            from apps.api.usage import FEATURE_RETRIEVAL_JUDGE, emit_completion_usage

            emit_completion_usage(
                FEATURE_RETRIEVAL_JUDGE, resp, fallback_model=self.model
            )
            return _parse_verdict(resp.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001 — judge failure must not kill the eval
            log.exception("retrieval judge call failed")
            return JudgeVerdict(error=f"{type(exc).__name__}: {exc}")


def _parse_verdict(text: str) -> JudgeVerdict:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return JudgeVerdict(error="unparseable judge JSON")
    if not isinstance(data, dict):
        return JudgeVerdict(error="judge JSON not an object")
    answerable = str(data.get("answerable", "")).strip().lower()
    if answerable not in _ANSWERABLE:
        answerable = "no"
    per_case = []
    raw_pc = data.get("per_case")
    if isinstance(raw_pc, list):
        for item in raw_pc:
            if isinstance(item, dict):
                rel = str(item.get("relevance", "")).strip().lower()
                per_case.append({
                    "case": str(item.get("case", "")).strip(),
                    "relevance": rel if rel in _RELEVANCE else "off",
                })
    return JudgeVerdict(
        answer=str(data.get("answer", "")).strip(),
        answerable=answerable,
        best_case=str(data.get("best_case", "")).strip(),
        controlling_present=bool(data.get("controlling_present", False)),
        stale_warning=str(data.get("stale_warning", "")).strip(),
        per_case=per_case,
        rationale=str(data.get("rationale", "")).strip(),
    )


def default_judge() -> RetrievalJudge | None:
    if getattr(settings, "OPENAI_API_KEY", ""):
        return OpenAIRetrievalJudge()
    return None
