#!/usr/bin/env python
"""STANDALONE EXPERIMENT — delete freely. Not imported by anything.

Prototype of the "web adverse-finding layer" (Accuracy Program §3c, PR9-shaped):

    user question
      → corpus retrieval (prod-like natural config: vector+rerank, trigram off,
        authority blend)
      → for the top caselaw hits, ask an OpenAI web-search call: "is this case
        still good law — any overruling / statutory supersession out there?"
      → if the web says ADVERSE: verify against OUR corpus — does the claimed
        superseding/overruling authority resolve here (statute lookup, reporter
        cite, case-name heading match)? And did the citator's treatment flag
        already know?

Success looks like: the layer flags Pexa (superseded by §§ 622.4/668.14A — the
known citator blind spot) and Godfrey (overruled by Burnett — which the citator
DOES know, so it should show up as "already known"), while staying quiet on
good-law cases. Failure looks like: noise on good-law cases, or nothing caught.

Run (from backend/):
    .venv/bin/python benchmarks/web_adverse_layer_test.py
    .venv/bin/python benchmarks/web_adverse_layer_test.py --cases-per-q 4 --questions 10

Writes benchmarks/web_adverse_layer_results.json with the full detail.
Spends OpenAI credit (~1 web-search call per checked case) and Voyage rerank.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.corpus.models import Node, ReporterCitation  # noqa: E402
from apps.corpus.services.lookups import lookup_citation  # noqa: E402
from apps.corpus.services.retrieval import retrieve_context  # noqa: E402

EVAL_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "apps", "api", "data", "chat_eval_adversarial.json",
)

WEB_MODELS = ["gpt-5-mini", "gpt-4o"]  # first that accepts web_search wins

WEB_PROMPT = """You are checking whether an Iowa appellate case is still good law.

Case: {heading}
Citation(s): {citation}

Search the web for credible indications this case has been overruled, abrogated,
superseded by statute, or otherwise negatively treated (court opinions,
legislative history, bar journals, reputable annotators). Distinguish real
negative treatment from mere criticism or distinguishing.

Reply with ONLY a JSON object, no prose:
{{"adverse": true/false,
  "kind": "overruled" | "superseded_by_statute" | "caution" | "none",
  "by": "<the overruling case or superseding statute, as specifically as possible>",
  "evidence": "<one short quoted/paraphrased sentence>",
  "source_url": "<best source url or empty>"}}

adverse=false with kind "none" if it appears to be good law or you find nothing
credible. Do not guess: an empty result is better than a fabricated one."""


SECTION_RE = re.compile(r"\b(\d{1,3}[A-Z]?\.\d+[A-Z]?)\b")
REPORTER_RE = re.compile(r"\b(\d{1,4})\s+(N\.W\.\s?[23]?d?|Iowa)\s+(\d{1,5})\b")


def web_check(client, model: str, heading: str, citation: str) -> dict:
    resp = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=WEB_PROMPT.format(heading=heading, citation=citation or "(none)"),
    )
    text = (resp.output_text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return {"adverse": False, "kind": "parse_error", "by": "", "evidence": text[:200], "source_url": ""}
    if not isinstance(data, dict):
        return {"adverse": False, "kind": "parse_error", "by": "", "evidence": "", "source_url": ""}
    return {
        "adverse": bool(data.get("adverse")),
        "kind": str(data.get("kind") or "none"),
        "by": str(data.get("by") or ""),
        "evidence": str(data.get("evidence") or "")[:300],
        "source_url": str(data.get("source_url") or ""),
    }


def corpus_verify(by: str) -> dict:
    """Can OUR corpus resolve the authority the web claims did the damage?"""
    out = {"verified": False, "matches": []}
    for sec in SECTION_RE.findall(by)[:4]:
        try:
            r = lookup_citation(f"Iowa Code § {sec}")
        except Exception:
            continue
        if getattr(r, "node", None) is not None:
            out["verified"] = True
            out["matches"].append(f"statute {sec}: {r.node.heading[:60]}")
    for vol, rep, page in REPORTER_RE.findall(by)[:4]:
        rep_norm = rep.replace(" ", "")
        if ReporterCitation.objects.filter(
            reporter=rep_norm, volume=vol, page=page, to_node__isnull=False
        ).exists():
            out["verified"] = True
            out["matches"].append(f"case cite {vol} {rep_norm} {page}")
    if not out["verified"]:
        # Case-name fallback: "Burnett v. Smith" -> heading icontains both names.
        m = re.search(r"([A-Z][A-Za-z']+)\s+v\.?\s+([A-Z][A-Za-z']+)", by)
        if m:
            qs = Node.objects.filter(
                source__slug="iowa-caselaw",
                heading__icontains=m.group(1),
            ).filter(heading__icontains=m.group(2))[:1]
            if qs:
                out["verified"] = True
                out["matches"].append(f"case name: {qs[0].heading[:60]}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=int, default=10)
    ap.add_argument("--cases-per-q", type=int, default=3)
    args = ap.parse_args()

    if not settings.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY not set")
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    queries = json.load(open(EVAL_FILE))["queries"][: args.questions]
    web_model: str | None = None
    results = []
    checked = adverse = verified = known = novel = unresolved = 0
    seen_clusters: set[int] = set()

    for qi, entry in enumerate(queries, 1):
        question = entry["question"]
        print(f"\n=== Q{qi}: {question[:100]}...")
        ctx = retrieve_context(
            question,
            use_trigram=False,
            authority_weight=0.25,
            display_limit=10,
            enrich_bodies=False,
        )
        case_passages = [
            p for p in ctx.passages if p.source_slug == "iowa-caselaw"
        ][: args.cases_per_q]
        if not case_passages:
            print("  (no caselaw in top results — skipped)")
            continue

        for p in case_passages:
            dedupe_key = p.cluster_id
            row = {
                "question": qi,
                "case": p.heading,
                "citation": p.citation,
                "citator_status": p.treatment.status,
                "citator_label": p.treatment.label,
            }
            if dedupe_key in seen_clusters:
                # Same case surfaced by an earlier question this run — reuse
                # nothing, just skip the duplicate web spend.
                continue
            seen_clusters.add(dedupe_key)
            checked += 1

            verdict = None
            for model in ([web_model] if web_model else WEB_MODELS):
                try:
                    verdict = web_check(client, model, p.heading, p.citation)
                    web_model = model
                    break
                except Exception as exc:  # try the next model once
                    print(f"  ! web_search via {model} failed: {exc}")
            if verdict is None:
                row["error"] = "all web models failed"
                results.append(row)
                continue

            row["web"] = verdict
            flag = "  -  good law per web"
            if verdict["adverse"]:
                adverse += 1
                ver = corpus_verify(verdict["by"])
                row["corpus_verification"] = ver
                citator_knew = p.treatment.status in ("negative", "caution")
                row["citator_knew"] = citator_knew
                if ver["verified"]:
                    verified += 1
                    if citator_knew:
                        known += 1
                        flag = f"  ⚑ ADVERSE ({verdict['kind']} by {verdict['by'][:60]}) — corpus-verified, citator ALREADY KNEW"
                    else:
                        novel += 1
                        flag = f"  ★ NOVEL CATCH ({verdict['kind']} by {verdict['by'][:60]}) — corpus-verified, citator did NOT know"
                else:
                    unresolved += 1
                    flag = f"  ? ADVERSE per web ({verdict['kind']} by {verdict['by'][:60]}) — could NOT resolve in corpus (web wrong, or corpus gap)"
            print(f"  {p.heading[:70]} [{p.citation[:30]}] citator={p.treatment.status}")
            print(flag)
            results.append(row)
            time.sleep(1)  # be polite to the API

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "web_adverse_layer_results.json")
    json.dump({"web_model": web_model, "summary": {
        "cases_checked": checked, "adverse": adverse,
        "corpus_verified": verified, "citator_already_knew": known,
        "novel_catches": novel, "unresolved": unresolved,
    }, "rows": results}, open(out_path, "w"), indent=2)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print(f"  web model:            {web_model}")
    print(f"  cases checked:        {checked}")
    print(f"  adverse per web:      {adverse}")
    print(f"    corpus-verified:    {verified}")
    print(f"      citator knew:     {known}   (tripwire redundant but consistent)")
    print(f"      NOVEL catches:    {novel}   (the value of the layer)")
    print(f"    unresolved:         {unresolved}   (web wrong, or corpus gap)")
    print(f"  detail: {out_path}")


if __name__ == "__main__":
    main()
