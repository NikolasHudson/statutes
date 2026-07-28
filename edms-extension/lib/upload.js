// PARKED FOR v2 — not wired up in v1.
//
// v1 ships without cloud saving, so nothing imports this module. It is kept
// (rather than deleted) because it is the only copy: the extension is not in
// git history yet. The matching server endpoints are preserved behind
// EDMS_CLOUD_ENABLED. Exclude this file from the Web Store build until v2.

// The upload half of the save flow: bytes go from the court to Microsoft
// without passing through Hudson.
//
//   1. the server minted an upload session and gave us its URL
//   2. we fetch the PDF from the court with the user's own session
//   3. we PUT it to that URL in chunks
//   4. the server confirms with Graph that the item is really there
//
// The URL carries its own authorization — it is scoped by Microsoft to one
// file, expires on its own, and needs neither a Hudson credential nor a
// Microsoft token. That is what makes step 3 safe to do from a browser.
//
// Chunk size: Graph requires a multiple of 320 KiB for every chunk except the
// last, and recommends 5–10 MiB. 5 MiB keeps a retry cheap on a bad connection
// without making the round-trip count silly for a 200 KB motion — and a filing
// under one chunk is a single PUT, which is the common case.

const CHUNK_MULTIPLE = 320 * 1024;
const CHUNK_SIZE = 16 * CHUNK_MULTIPLE; // 5 MiB
const MAX_ATTEMPTS = 3;

/** Fetch the filing from the court, using the user's own logged-in session. */
export async function fetchFiling(url) {
  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) throw new Error(`Could not download the filing (${resp.status}).`);
  const blob = await resp.blob();
  if (!blob.size) throw new Error("The court returned an empty file.");
  return blob;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * PUT `blob` to a Graph upload session. Resolves with the created driveItem
 * (Graph returns it on the final chunk, 200/201).
 *
 * Microsoft's own guidance is to retry a failed chunk rather than restart the
 * upload — the session remembers what it has. 429/5xx get one backoff each;
 * anything else is terminal, because retrying a 4xx just wastes the user's
 * time before showing them the same error.
 */
export async function uploadToSession(uploadUrl, blob, { onProgress } = {}) {
  const total = blob.size;
  let offset = 0;

  while (offset < total) {
    const end = Math.min(offset + CHUNK_SIZE, total);
    const chunk = blob.slice(offset, end);
    let attempt = 0;
    let resp = null;

    for (;;) {
      attempt += 1;
      try {
        resp = await fetch(uploadUrl, {
          method: "PUT",
          headers: {
            "Content-Range": `bytes ${offset}-${end - 1}/${total}`,
            "Content-Length": String(end - offset),
          },
          body: chunk,
        });
      } catch (err) {
        if (attempt >= MAX_ATTEMPTS) throw new Error(`Upload failed: ${err.message}`);
        await sleep(500 * attempt);
        continue;
      }
      if (resp.status === 429 || resp.status >= 500) {
        if (attempt >= MAX_ATTEMPTS) {
          throw new Error(`OneDrive is unavailable (${resp.status}). Try again shortly.`);
        }
        const retryAfter = Number(resp.headers.get("Retry-After")) || attempt;
        await sleep(Math.min(retryAfter, 10) * 1000);
        continue;
      }
      break;
    }

    if (resp.status === 200 || resp.status === 201) {
      const item = await resp.json().catch(() => ({}));
      onProgress?.(1);
      return item;
    }
    if (resp.status !== 202) {
      const text = await resp.text().catch(() => "");
      throw new Error(`OneDrive rejected the upload (${resp.status}). ${text.slice(0, 160)}`);
    }

    // 202 Accepted — Graph reports the ranges it still wants. Trust its answer
    // over our own arithmetic: a retried chunk it already has would otherwise
    // leave us uploading a range it will refuse.
    const body = await resp.json().catch(() => ({}));
    const next = (body.nextExpectedRanges || [])[0];
    offset = next ? Number(String(next).split("-")[0]) : end;
    onProgress?.(Math.min(offset / total, 0.99));
  }

  // Every chunk returned 202 and we ran out of file — Graph never handed back
  // an item, so we cannot claim this worked. The server's own verification
  // (which is what actually decides) will agree.
  throw new Error("Upload finished without a confirmation from OneDrive.");
}

/** Cancel a session so an abandoned upload doesn't linger for its full TTL. */
export async function cancelSession(uploadUrl) {
  try {
    await fetch(uploadUrl, { method: "DELETE" });
  } catch {
    /* best effort — the session expires on its own */
  }
}
