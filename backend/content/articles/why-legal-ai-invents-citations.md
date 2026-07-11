---
title: "Why Legal AI Keeps Inventing Citations — and What Grounding Actually Fixes"
slug: why-legal-ai-invents-citations
category: Grounding
date: 2026-06-24
read_minutes: 8
lede: >-
  Fluent text and trustworthy text are not the same thing. Here's the
  difference between an AI that sounds right and one you can hand to a court.
excerpt: >-
  Fluent text and trustworthy text are not the same thing. The difference
  between an AI that sounds right and one you can hand to a court — and why
  most legal AI tools make the same mistake look more convincing.
tags: [Grounding, Hallucination, Citations, RAG, Legal AI]
published: true
---

In June 2023, two New York lawyers were sanctioned for submitting a brief full of cases that did not exist. They hadn't made them up — a chatbot had. It produced citations, parallel reporters, even fabricated internal quotations, all formatted perfectly. The lawyers filed it. The cases were fiction.

That episode gets told as a story about careless lawyers. It's really a story about how generative AI works — and why most legal AI tools, even today, are built to make the same mistake look more convincing.

## A $5,000 lesson in fluency

The model wasn't broken. It did exactly what it was designed to do: produce the most plausible-sounding continuation of the prompt. A citation is a highly patterned object — a case name, a volume, a reporter, a page, a year. A system trained on millions of them can generate a flawless-looking one without any case behind it. Fluency was never the problem. Fluency was the trap.

## Fluency is not grounding

A large language model is, at heart, a next-token predictor. Ask it a question and it doesn't look anything up — it writes the words most likely to follow your question, given everything it absorbed in training. For prose, that's remarkable. For law, it's dangerous, because the part you most need to trust — the citation — is exactly the part the model is most willing to invent.

This is why "we use GPT-4" tells you almost nothing about whether a legal tool is safe. The base model is the same one that fabricated those cases. What matters is everything wrapped around it.

## What grounding actually means

Grounding flips the order of operations. Instead of asking the model to answer from memory, you first retrieve the actual authoritative text — the statute, the rule, the decision — and hand it to the model as the only material it's allowed to reason from. The model's job stops being "recall the law" and becomes "summarize and explain *this* text, and cite it."

At Hudson, that material is a maintained corpus of the Iowa Code, Court Rules, and caselaw — the currently effective, human-reviewed text, with its citation, effective date, and enacting session law attached. Retrieval is hybrid: full-text and trigram matching for precision, vector embeddings for the semantically-phrased question, fused together so the on-point provision surfaces whether you typed its number or described what it does.

> A citation you have to double-check isn't a citation. It's a lead.

## The step most tools skip

Here's the uncomfortable part: grounding alone is necessary but not sufficient. Give a model the right passage and it can still paraphrase a quote slightly wrong, attribute it to the neighboring section, or carry over a citation from context that doesn't actually support the sentence it's attached to. Retrieval reduces hallucination. It doesn't eliminate it.

So Hudson adds a step that runs *after* the model writes its answer and *before* you ever see it: a deterministic check that walks every citation and every quoted span and confirms it against the source text. A quote that isn't verbatim, or a citation that points at text that doesn't support the claim, gets caught — not by another model asked to grade itself, but by code comparing strings to the corpus.

> **Why deterministic, not another model?**
> Asking a second LLM "is this right?" inherits the same failure mode you were trying to escape. A string-and-citation check against the source is boring, fast, and — crucially — can't be charmed by a confident-sounding answer.

## What it looks like in practice

Ask Hudson whether Iowa recognizes a private right of action under its Consumer Fraud Act, and you get a direct answer anchored to **Iowa Code § 714H.5** — with the citation linked to the official text, the effective date shown, and a small badge confirming every citation in the answer was verified against the source.

The more important behavior is the one you don't see advertised: when the corpus doesn't actually support an answer, Hudson tells you that, instead of producing a plausible-looking case to fill the gap. "I can't find support for that" is, in legal research, a feature.

## The bottom line

The lawyers in that 2023 case weren't undone by a bad model. They were undone by a tool that optimized for sounding right over being right — and gave them no way to tell the difference. Grounding, real citations, and verification aren't features you bolt on for marketing. They're the difference between a draft you have to re-check line by line and an answer you can put your name on.
