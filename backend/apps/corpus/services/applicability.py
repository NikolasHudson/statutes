"""PR8: domain-applicability check — the "real statute, wrong domain" gap.

The deterministic gate proves a cited authority EXISTS, is QUOTED accurately,
and is CURRENT. It cannot tell whether the authority's subject matter governs
the user's fact pattern: Iowa Code § 554.2718 (the UCC sale-of-goods
liquidated-damages rule) verifies perfectly while being misapplied to a
residential lease — the failure that motivated this module. This is the
statutory sibling of PR5's claim-NLI (which catches caselaw misgrounding).

One cheap LLM call per answer, batched over every resolved citation: given
the user's facts and the cited authorities (citation + section heading), the
model classifies each as ``governs`` / ``analogy`` / ``inapplicable``. Only
``inapplicable`` — wrong domain presented as if it governed — is reported as
a problem; a candid analogy is legitimate lawyering.

Flag-gated OFF by default (``RAG_APPLICABILITY_CHECK``), same posture as the
other LLM verification layers: deterministic v1 paths always run, LLM
judgment is opt-in per deploy and a no-op without an OpenAI key. Failures
never break verification — no verdict just means no advisory line.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-5-mini"

_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

_SYSTEM_PROMPT = (
    "You check DOMAIN FIT for legal citations in a draft research answer. "
    "Given the user's question (fact pattern) and the authorities the draft "
    "cites, decide for each authority whether its own act/chapter's subject "
    "matter directly governs the fact pattern.\n\n"
    "Categories:\n"
    "- \"governs\": the authority's body of law covers this subject matter "
    "(e.g. Iowa Code ch. 562A for a residential landlord-tenant dispute).\n"
    "- \"analogy\": a different body of law, legitimately usable as analogy "
    "or background (e.g. UCC principles discussed as comparison).\n"
    "- \"inapplicable\": a different body of law presented as if it governed "
    "(e.g. UCC art. 2 sale-of-goods rules applied to a residential lease).\n\n"
    "Judge domain fit ONLY — not whether the legal analysis is correct.\n"
    "Reply with JSON only: {\"verdicts\": [{\"i\": <authority index>, "
    "\"fit\": \"governs\"|\"analogy\"|\"inapplicable\", "
    "\"reason\": \"<at most 25 words>\"}]}"
)


class ApplicabilityChecker(Protocol):
    def check(
        self, question: str, authorities: list[dict[str, str]]
    ) -> list[dict[str, Any]]: ...


@dataclass
class OpenAIApplicabilityChecker:
    """Default checker: one JSON-mode completion over all cited authorities."""

    api_key: str = ""
    model: str = _DEFAULT_MODEL

    def _key(self) -> str:
        return self.api_key or getattr(settings, "OPENAI_API_KEY", "")

    def check(
        self, question: str, authorities: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        if not authorities or not question.strip() or not self._key():
            return []
        try:
            from openai import OpenAI
        except ImportError:
            return []

        listing = "\n".join(
            f"{i}. {a['raw']} — \"{a.get('heading') or '(no heading)'}\""
            for i, a in enumerate(authorities)
        )
        user = (
            f"USER'S QUESTION / FACT PATTERN:\n{question[:4000]}\n\n"
            f"AUTHORITIES CITED BY THE DRAFT ANSWER:\n{listing}"
        )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if not any(self.model.startswith(p) for p in _REASONING_PREFIXES):
            kwargs["temperature"] = 0
        try:
            client = OpenAI(api_key=self._key())
            completion = client.chat.completions.create(**kwargs)
            data = json.loads(completion.choices[0].message.content or "{}")
        except Exception:  # noqa: BLE001 — a model failure must not break verify
            logger.exception("applicability check failed")
            return []
        return _parse_verdicts(data, authorities)


def _parse_verdicts(
    data: Any, authorities: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Defensive parse: keep only well-formed verdicts with in-range indices
    and known categories; anything else is dropped (no verdict, no problem)."""
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for v in (data.get("verdicts") if isinstance(data, dict) else None) or []:
        if not isinstance(v, dict):
            continue
        try:
            i = int(v.get("i"))
        except (TypeError, ValueError):
            continue
        fit = str(v.get("fit") or "").strip().lower()
        if i in seen or not (0 <= i < len(authorities)):
            continue
        if fit not in ("governs", "analogy", "inapplicable"):
            continue
        seen.add(i)
        out.append(
            {
                **authorities[i],
                "fit": fit,
                "reason": str(v.get("reason") or "")[:200],
            }
        )
    return out


def default_checker() -> ApplicabilityChecker | None:
    """The checker verify_answer uses when ``RAG_APPLICABILITY_CHECK`` is on;
    ``None`` (check silently skipped) when no OpenAI key is configured."""
    if not getattr(settings, "OPENAI_API_KEY", ""):
        return None
    return OpenAIApplicabilityChecker()
