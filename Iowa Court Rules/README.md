# Iowa Court Rules — Source Snapshot

Snapshot of every Iowa Court Rules chapter PDF as published on legis.iowa.gov for the **February 27, 2026** edition. Pulled on 2026-05-15 for designing the production scraper.

## What's here

- `pdfs/chapter-NN.pdf` — one PDF per chapter, 01–70 (zero-padded)
- `manifest.csv` — chapter number, title, page count, byte size, reserved flag, source URL, local path
- `probe.py` — extractor that converts PDFs into structured JSON. Standalone script (no Django imports) so the parsing logic can iterate fast.
- `probe.json` — the extractor's output: 70 chapters, 1,205 parsed rules with body text, comment text, division banner, and history brackets. This is the stable intermediate artifact that the Django ingestion app will consume — same shape pattern as `iowa_code_probe.json` for Iowa Code.
- `README.md` — this file

70 PDFs total, ~119 MB on disk. 48 chapters carry content; 22 are "Reserved" placeholders (single-page PDFs around 32–45 KB whose first page text is just `CHAPTER NN Reserved`). Of the 48 content chapters, 43 follow the `Rule N.M` structure and parse cleanly into 1,205 rules; 5 (chapters 3, 48, 61, 62, 63) use different document structures (Standard Forms, Canons, Roman-numeral standards) and need their own parsers — they sit in `probe.json` as zero-rule entries with a `parse_notes` flag.

## URL pattern

Every chapter is published at a predictable URL on legis.iowa.gov:

```
https://www.legis.iowa.gov/docs/ACO/CR/LINC/<MM-DD-YYYY>.chapter.<N>.pdf
```

- `<MM-DD-YYYY>` is the **publication date** of the current edition (`02-27-2026` as of this snapshot). The date string lives on the listings page — the scraper should read it from there rather than hard-code it, because it rolls forward when the Supreme Court adopts amendments.
- `<N>` is the chapter number as a plain integer (1–70), **not** zero-padded.
- The `LINC` URL 302-redirects to `…/docs/ACO/CourtRulesChapter/<MM-DD-YYYY>.<N>.pdf` (the canonical path). Either works; the `LINC` form is the one printed on the listings page, so prefer it.

Listings page (the index that drives discovery):
```
https://www.legis.iowa.gov/law/courtRules/courtRulesListings
```

Chapter numbering goes from 1 to 70 contiguously, with reserved gaps at: 18, 19, 24, 27–30, 50, 53–60, 64–69.

## Scrape design notes

- **Discovery is cheap.** Just iterate `chapter in 1..70` against the URL pattern after pulling the current publication date from the listings page. No need to parse a full TOC.
- **All PDFs extract as text** with `pypdf` — no OCR needed. The first-page text for content chapters starts with `CHAPTER N <TITLE>` (or a running-header variant). Reserved chapters have first-page text ending in `CHAPTER N Reserved`, which is a reliable detector.
- **Sizes vary by 3+ orders of magnitude.** Biggest chapters: Probate (ch 7, 108 pages / 23 MB), Criminal Procedure (ch 2, 103 pages / 22 MB), Juvenile (ch 8, 58 pages / 17 MB), Civil (ch 1, 130 pages / 6.8 MB). Smallest content chapters are under 100 KB.
- **Structure inside the PDF** is rule-numbered (`Rule N.M`) under a chapter header, sometimes grouped into Divisions. Headers/footers and section dividers will need to be stripped during text extraction — the running header repeats on every page (`<MONTH> <YEAR> <TITLE> Ch <N>, p.<x>`).
- **Edition cadence.** legis.iowa.gov publishes a single dated edition for the whole court-rules set; the date changes when the Supreme Court issues amendments. The scraper should record this date as the snapshot's effective date.
- **No HTML or RTF equivalents.** Unlike the Iowa Code, court rules only ship as per-chapter PDFs. (Same observation as `reference_iowa_code_urls.md` predicted — universal coverage is PDF-only.)

## Reproduce the download

```bash
cd "Iowa Court Rules" && mkdir -p pdfs
DATE=02-27-2026  # read this from courtRulesListings before bulk-running
for ch in $(seq 1 70); do
  curl -sL --max-time 120 \
    -o "pdfs/chapter-$(printf '%02d' $ch).pdf" \
    "https://www.legis.iowa.gov/docs/ACO/CR/LINC/${DATE}.chapter.${ch}.pdf"
done
```

## Reproduce probe.json

```bash
cd "Iowa Court Rules"
python3 probe.py $(seq 1 70)   # all 70 chapters → probe.json
python3 probe.py 32             # one chapter at a time also works
```

Requires `pdfplumber` (`pip install pdfplumber`). Run takes ~25 s for all 70 chapters.

## probe.json schema

```jsonc
{
  "edition_date": "2026-02-27",
  "source_base_url": "https://www.legis.iowa.gov/docs/ACO/CR/LINC/02-27-2026.chapter.{chapter}.pdf",
  "summary": { "chapters_probed": 70, "chapters_ok": 43, "total_rules": 1205 },
  "samples": [
    {
      "chapter": "32",
      "chapter_title": "Iowa Rules of Professional Conduct",
      "reserved": false,                       // true for 22 chapters that have no real content
      "chapter_pdf_url": "https://…/02-27-2026.chapter.32.pdf",
      "page_count": 89,
      "rule_count": 59,
      "rules": [
        {
          "number": "32:1.1",                   // canonical rule number, normalized (no trailing . or :)
          "heading": "Competence",              // pulled from the chapter TOC (correct case, full wrap)
          "division": "CLIENT-LAWYER RELATIONSHIP",  // last ALL-CAPS banner seen before the rule, "" if none
          "body_text": "A lawyer shall provide …",   // rule prose; paragraphs separated by \n\n
          "body_chars": 197,
          "comment_text": "Legal Knowledge and Skill\n\n[1] In determining …",
          "comment_chars": 4713,
          "history_brackets": ["[Court Order April 20, 2005, effective July 1, 2005; …]"],
          "reserved": false                     // true for Reserved-rule placeholders with no body
        }
      ],
      "parse_notes": []                         // non-empty when the chapter uses a non-Rule structure
    }
  ]
}
```

Field-by-field notes:

- **`number`** — canonical rule number with stray trailing punctuation stripped. Ch 32 uses the `32:1.1` form (colon between chapter and rule); other chapters use `1.402` (no colon). The probe reconciles both.
- **`heading`** — taken from the TOC entry, which has the correct case and includes wrapped-line continuations. The body's rule header (often ALL CAPS or with a trailing period and the first body sentence on the same line) is split during extraction so the heading stays clean and the body's first sentence becomes the body's first paragraph.
- **`division`** — best-effort attribution. For multi-line ALL-CAPS banners (e.g. chapter 51's CANON 2 followed by 3 lines of description), we take the last line of the block — the most specific banner near the rule. Imperfect for chapters with deeply nested subdivisions; treat as a categorization hint, not a structural primary key.
- **`body_text` vs `comment_text`** — the split happens at the literal `Comment` line that appears in many chapters (especially chapter 32 Prof. Conduct). Chapters without a Comment section put everything into `body_text`. Sub-labels inside Comment sections (e.g. "Legal Knowledge and Skill") are preserved as plain text within `comment_text` rather than split into separate fields — bold/italic distinctions aren't recoverable from positional PDF text and a wrong split would be worse than no split.
- **`history_brackets`** — every `[Court Order …]`, `[Report …]`, `[Amended …]` block that closed the rule. Multi-line brackets are joined back into a single string each.
- **`reserved`** at rule level — true for `Rule N.M Reserved` placeholders (e.g. ch 32 rule 32:2.2). At chapter level — true for the 22 reserved chapters.

## Known limitations

- **Five chapters return 0 rules** with a `parse_notes` flag: chapters 3 (Small Claims Forms), 48 (Interpreters Code of Conduct), 61–63 (Standards of Practice for various lawyer roles). They use Form/Canon/Roman-numeral numbering that the current `Rule N.M` extractor doesn't recognize. Total rule count would grow to a few hundred more if these are handled — separate parser to be written when those chapters' content matters.
- **Division attribution is best-effort.** Chapters with multi-line canon descriptions (ch 51) get the description's last line as the division rather than "CANON 1/2/3/4". Acceptable for categorization; not authoritative structure.
