# Verify-Document — Production Run Analysis

> Analysis of a live `verify_document` run against a production demand letter
> (Iowa Code citations). Run summary: **13 citations checked — 10 green / 3 yellow / 0 red — 1m 9s.**

---

## Bottom line

This is a strong production result, and reading it against the code, the grading is
defensible row-by-row. 13/13 resolved, 0 false reds, and the three yellows are all
*correctly* yellow. The tool is discriminating in exactly the way you want: it greens
clean paraphrases and flags the ones that reach past the cited text. For an
AI-assisted demand letter, "0 fabricated citations, 3 slightly-overreaching
paraphrases" is the right answer.

## The three "partially supported" calls are all legitimate

Each yellow is a case where the *sentence* claims more than the *cited subsection*
says — which is precisely what `_finalize` grades (it sends the whole claim sentence
to the semantic checker against the provision body):

- **§ 554.2316(1)** — the letter says "no disclaimer can be construed to negate your
  own affirmative written descriptions." The statute only makes negation inoperative
  "*to the extent that such construction is unreasonable*." The letter states it as
  absolute; the statute is conditional. Correctly partial.
- **§ 714H.5(4) ("would approach $219,849.30")** — the statute supports "up to three
  times actual damages" but obviously not the specific dollar computation bolted onto
  the sentence. Correctly partial.
- **§ 714H.5(4) ("punitive damages, attorney fees, costs…")** — the sentence bundles
  remedies that live in *other* subsections (fees are .5(2), punitives aren't in 714H
  at all) under a single .5(4) cite. Correctly partial.

So the yellows aren't noise — each is a real "your cite is doing more work than the
text supports" flag. That's genuinely useful to a drafting lawyer.

## The one thing this run quietly reveals: grounding is section-level, not subsection-level

Look at the first `§ 714H.5(4)` and the `§ 714H.5(2)` rows — both show a **Source
containing *both* subsection 4 and subsection 2**. That's not a glitch; it's
`_build_findings` using `best.version.body_text`
(`backend/apps/corpus/services/verify_document.py:399`), which is the whole
**714H.5** section body. The `(4)` / `(2)` subdivisions parse, but grounding doesn't
narrow to them.

Practical consequence: **a citation to the wrong subsection of the right section will
still pass.** If someone cited `§ 714H.5(3)` for the attorney-fees language, it would
still green, because subsection 2's fee text is in the same grounding blob. For most
demand-letter work that's fine, but for a verification tool whose whole pitch is
precision, it's the gap to document and decide on deliberately.

## What this run does *not* prove

- **The red path is untested here.** 0 reds is great for this document but means we
  didn't watch a failure fire. Run a negative control — paste in a fabricated cite
  (`§ 714H.9`) and an altered quote — and confirm it goes red.
- **Range cites collapse.** `§ 554.2313(1)(a)-(b)` shows up as one `(1)(a)` row;
  worth confirming `(1)(b)` is actually being checked and not just swept into the same
  node body.

## Minor UX note

The rollup detail is generic ("Cited language only partially matches the source").
For the `$219,849.30` row, the *useful* feedback is "the dollar figure isn't in the
statute." The semantic checker already returns `verdict.evidence` — surfacing *why*
it's partial (which span overran the source) would make the yellows actionable
instead of just cautionary.

---

## Raw run output

13 citations checked
10
3
0
1m 9s

### Iowa Code Chapter 714H — Iowa Code
Citation format valid and resolves to a current provision.
Form: Iowa Code ch. 714H
Citation format valid and resolves to a current provision.

### Iowa Code § 714H.3 — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "Your misrepresentations regarding new parts, your concealment of the use of used
> components, and your false claims about the head and header and overheating
> constitute deception, fraud, and omissions of material fact in violation of Iowa
> Code § 714H.3."

Source: A person shall not engage in a practice or act the person knows or reasonably
should know is an unfair practice, deception, fraud, false pretense, or false promise,
or the misrepresentation, concealment, suppression, or omission of a material fact,
with the intent that others rely upon the unfair practice, deception, fraud, false
pretense, false promise, misrepresentation, concealment, suppression, or omission in
connection with the advertisement, sale, or lease of consumer merchandise... For the
purposes of this chapter, a claimant alleging an unfair practice, deception, fraud,
false pretense, false promise, or misrepresentation must prove that the prohibited
practice related to a material fact or facts.

### Iowa Code § 714H.5(4) — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "If a violation of this chapter is found, the willful and wanton nature of your
> conduct, evidenced by your multiple admissions, the pattern of similar complaints
> from other customers, and your repeated false statements when confronted, would
> support an award of statutory damages up to three times Mr. Leisz's actual damages
> under Iowa Code § 714H.5(4), along with mandatory attorney fees and costs under §
> 714H.5(2). -"

Source: 4. If the finder of fact finds by a preponderance of clear, convincing, and
satisfactory evidence that a prohibited practice or act in violation of this chapter
constitutes willful and wanton disregard for the rights or safety of another, in
addition to an award of actual damages, statutory damages up to three times the amount
of actual damages may be awarded to a prevailing consumer. 2. If the court finds that a
person has violated this chapter and the consumer is awarded actual damages, the court
shall award to the consumer the costs of the action and to the consumer's attorney
reasonable fees.

### § 714H.5(2) — Iowa Code
Citation valid and cited language is supported by the source. Form: Iowa Code §
714H.5(2). **Supported** (paraphrase)

> "If a violation of this chapter is found, the willful and wanton nature of your
> conduct, evidenced by your multiple admissions, the pattern of similar complaints
> from other customers, and your repeated false statements when confronted, would
> support an award of statutory damages up to three times Mr. Leisz's actual damages
> under Iowa Code § 714H.5(4), along with mandatory attorney fees and costs under §
> 714H.5(2). -"

Source: 4. If the finder of fact finds by a preponderance of clear, convincing, and
satisfactory evidence that a prohibited practice or act in violation of this chapter
constitutes willful and wanton disregard for the rights or safety of another, in
addition to an award of actual damages, statutory damages up to three times the amount
of actual damages may be awarded to a prevailing consumer. 2. If the court finds that a
person has violated this chapter and the consumer is awarded actual damages, the court
shall award to the consumer the costs of the action and to the consumer's attorney
reasonable fees.

### Iowa Code § 554.2313 — Iowa Code
Citation format valid and resolves to a current provision.
Citation format valid and resolves to a current provision.

### Iowa Code § 554.2313(1)(a) — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "Under Iowa Code § 554.2313(1)(a)-(b), these written affirmations of fact and
> descriptions of the goods became part of the basis of the bargain and created
> express warranties."

Source: Any affirmation of fact or promise made by the seller to the buyer which
relates to the goods and becomes part of the basis of the bargain creates an express
warranty that the goods shall conform to the affirmation or promise. Any description of
the goods which is made part of the basis of the bargain creates an express warranty
that the goods shall conform to the description.

### Iowa Code § 554.2316(1) — Iowa Code
Cited language only partially matches the source. **Partially supported** (paraphrase)

> "Any attempt to disclaim these warranties is inoperative under Iowa Code §
> 554.2316(1) because no disclaimer can be construed to negate your own affirmative
> written descriptions of the goods. -"

Source: Words or conduct relevant to the creation of an express warranty and words or
conduct tending to negate or limit warranty shall be construed wherever reasonable as
consistent with each other; but subject to the provisions of this Article on parol or
extrinsic evidence (section 554.2202) negation or limitation is inoperative to the
extent that such construction is unreasonable.

### Iowa Code § 554.2314 — Iowa Code
Citation format valid and resolves to a current provision.
Citation format valid and resolves to a current provision.

### Iowa Code § 554.2315 — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "V. Breach of Implied Warranty of Fitness for a Particular Purpose (Iowa Code §
> 554.2315)."

Source: Where the seller at the time of contracting has reason to know any particular
purpose for which the goods are required and that the buyer is relying on the seller's
skill or judgment to select or furnish suitable goods, there is unless excluded or
modified under section 554.2316 an implied warranty that the goods shall be fit for
such purpose.

### Iowa Code § 714H.5(4) — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "It does not include the original $133,948.00 paid to you, enhanced statutory damages
> under Iowa Code § 714H.5(4), punitive damages, attorney fees, or litigation costs,
> all of which are expressly reserved."

Source: 4. If the finder of fact finds by a preponderance of clear, convincing, and
satisfactory evidence that a prohibited practice or act in violation of this chapter
constitutes willful and wanton disregard for the rights or safety of another, in
addition to an award of actual damages, statutory damages up to three times the amount
of actual damages may be awarded to a prevailing consumer.

### § 714H.5(4) — Iowa Code
Cited language only partially matches the source. Form: Iowa Code § 714H.5(4).
**Partially supported** (paraphrase)

> "If this matter proceeds to litigation and a violation of the Iowa Consumer Fraud Act
> is found, statutory damages under § 714H.5(4) could reach up to three times Mr.
> Leisz's actual damages, which based on the amount demanded alone would approach
> $219,849.30, without accounting for the additional categories of damages reserved
> above."

Source: 4. If the finder of fact finds by a preponderance of clear, convincing, and
satisfactory evidence that a prohibited practice or act in violation of this chapter
constitutes willful and wanton disregard for the rights or safety of another, in
addition to an award of actual damages, statutory damages up to three times the amount
of actual damages may be awarded to a prevailing consumer.

### Iowa Code § 714H.5(2) — Iowa Code
Citation valid and cited language is supported by the source. **Supported** (paraphrase)

> "Mr. Leisz will also seek attorney fees and costs as provided by Iowa Code §
> 714H.5(2)."

Source: If the court finds that a person has violated this chapter and the consumer is
awarded actual damages, the court shall award to the consumer the costs of the action
and to the consumer's attorney reasonable fees.

### Iowa Code § 714H.5(4) — Iowa Code
Cited language only partially matches the source. **Partially supported** (paraphrase)

> "If we do not receive payment or a satisfactory written response within seven (7)
> days, we will pursue all available legal remedies, including filing suit seeking
> actual damages, enhanced statutory damages under Iowa Code § 714H.5(4), punitive
> damages, attorney fees, costs, and all other available relief."

Source: 1. A consumer who suffers an ascertainable loss of money or property ... may
bring an action at law to recover actual damages. 2. If the court finds that a person
has violated this chapter and the consumer is awarded actual damages, the court shall
award to the consumer the costs of the action and to the consumer's attorney reasonable
fees. 4. ... statutory damages up to three times the amount of actual damages may be
awarded to a prevailing consumer.
