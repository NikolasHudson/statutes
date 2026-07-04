# Hudson Corpus — product screenshots

Drop product screenshots into this folder using the **exact filenames** below.
They appear automatically on the Corpus product page
(`/home-mockup/products/corpus`) — no code change needed. Until a file exists,
the page shows a labeled placeholder in that slot.

| File            | Where it shows                | Suggested screen to capture                                  |
| --------------- | ----------------------------- | ----------------------------------------------------------- |
| `assistant.png` | Hero (large, top of page)     | The assistant answering a question with inline citations + the "verifying citations" / verified state |
| `browse.png`    | "Browse" feature section      | The Library / `/browse` view — sources, search, results     |
| `reader.png`    | "Read" feature section        | A statute or case reader showing the effective text + citation |
| `search.png`    | "Search" feature section      | A search results page with ranked, cited hits + filters     |

## Capture tips

- **Aspect ratio:** frames are **16:10**. Capture at that ratio so nothing is
  cropped (the image is `object-cover`, anchored to the top).
- **Size:** export at **2×** for crisp display — e.g. **2560×1600** for the
  hero, **~1920×1200** for the feature shots. PNG (or WebP) preferred.
- **Browser chrome:** the page already draws a window frame (traffic lights +
  address bar), so capture the **app content only** — no need to include the
  real browser's toolbar.
- **Content:** light mode matches the surrounding page best. Use real corpus
  data (real Iowa Code §§ / case names) — it sells the grounding story.

You can also swap filenames/paths or aspect ratios in
`app/home-mockup/products/corpus/page.tsx` (the `SHOTS` map and each block's
`shot`) and `components/marketing/screenshot.tsx`.
