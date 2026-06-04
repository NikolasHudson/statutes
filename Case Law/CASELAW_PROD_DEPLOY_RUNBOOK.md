# Caselaw → Production deploy runbook

Ship the Iowa caselaw corpus + the Westlaw-style browse/case-console/display
features to production (DO App Platform app `statutes`, managed PG `iowa-db`).

This is **two independent tracks**: code rides the git push; schema + data are
applied to prod **by hand from the dev droplet** (the Dockerfile `CMD` is just
`gunicorn` — nothing runs `migrate` on deploy). The droplet is in `iowa-db`'s
Trusted Sources, so it can talk to prod directly.

## Verified pre-state (2026-06-04, before any change)

| Fact | prod | dev (source of the data) |
|---|---|---|
| corpus migration head | `0008_drop_body_text_trgm` | `0018` |
| `ingestion_caselaw` | absent | `0001` |
| nodes | 31,002 (max id **31,660**) | + 159,209 caselaw (ids **31,664–191,132**) |
| nodeversions | 29,062 (max id 29,638) | + 111,323 caselaw (ids 29,648–141,015) |
| `corpus_crossreference` | 0 rows | 693,497 caselaw edges |
| sources / nodetypes | source seq=3, nodetype seq=8 | iowa-caselaw=**4**, decision=**9**, opinion=**10** |
| DB size | 481 MB (10 GB-disk plan) | 3.1 GB |

**Why an id-preserving restore is safe:** prod is a faithful sequence-inherited
clone, so running migration `0011` in prod assigns the caselaw `Source` id **4**
and `NodeType`s **9/10** — exactly the ids the dumped rows reference. The caselaw
id bands sit cleanly **above** prod's existing corpus, and `crossreference` is
empty in prod. Constraint pre-checks (0010/0012) found **0** violations. The
load script still **hard-gates** on seed ids 4/9/10 and aborts on mismatch.

## Phase A — code (no prod risk)  ✅ done

Committed on `dev` as `54f1737` (feat: Westlaw browse + case console + display).
Backend: 408 tests, 1 known pre-existing failure
(`mcp_server …test_lookup_citation_returns_candidates_when_unresolved`).

## Phase B — prod DB (rehearsed against a throwaway prod clone first)

Working dir (non-repo, holds the ~860 MB dump): `/home/dev/caselaw-prod-dump/`.

### B1. Build the selective dump from dev (gzipped binary COPY)
```bash
PGURL="postgres://corpus:corpus@localhost:5432/corpus"; OUT=/home/dev/caselaw-prod-dump; mkdir -p "$OUT"
psql "$PGURL" -c "\copy (SELECT * FROM corpus_node WHERE source_id=4) TO STDOUT (FORMAT binary)" | gzip > "$OUT/node.bin.gz"
psql "$PGURL" -c "\copy (SELECT * FROM corpus_nodeversion WHERE node_id IN (SELECT id FROM corpus_node WHERE source_id=4)) TO STDOUT (FORMAT binary)" | gzip > "$OUT/nodeversion.bin.gz"
psql "$PGURL" -c "\copy (SELECT * FROM corpus_reportercitation) TO STDOUT (FORMAT binary)" | gzip > "$OUT/reportercitation.bin.gz"
psql "$PGURL" -c "\copy (SELECT * FROM corpus_crossreference WHERE source IN ('caselaw_link','caselaw_graph')) TO STDOUT (FORMAT binary)" | gzip > "$OUT/crossreference.bin.gz"
```

### B2. Backup prod (rollback artifact + rehearsal baseline)
```bash
PROD="$(tr -d '[:space:]' < /home/dev/statutes/.prod_db_url)"
NEWEST="$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)"
"$NEWEST/pg_dump" "$PROD" -Fc --no-owner --no-privileges -f "$OUT/prod_baseline.dump"
```

### B3. Rehearse on a fresh clone of current prod
```bash
ADMIN="postgres://corpus:corpus@localhost:5432/postgres"
REH="postgres://corpus:corpus@localhost:5432/corpus_rehearsal"
psql "$ADMIN" -c "DROP DATABASE IF EXISTS corpus_rehearsal;" -c "CREATE DATABASE corpus_rehearsal OWNER corpus;"
"$NEWEST/pg_restore" --no-owner --no-privileges -d "$REH" "$OUT/prod_baseline.dump"   # role/comment errors are harmless
./load_caselaw.sh "$REH"            # migrate + seed-gate + load + setval + verify
```
Expected verify line: **nodes=159209  versions=111323  reportercites=118783  xrefs=693497**.
Then drop the scratch DB: `psql "$ADMIN" -c "DROP DATABASE corpus_rehearsal;"`

### B4. Run against prod (off-peak)
```bash
./load_caselaw.sh "$PROD"
```
`load_caselaw.sh` (in the working dir): migrates corpus 0009–0018 + ingestion_caselaw 0001,
**gates** on seed ids 4/9/10, loads the 4 tables in one transaction with FKs deferred
(enforced at COMMIT), resets the four id sequences, and prints the verify counts.
Migrations are additive (new tables/cols/indexes, idempotent seeds, 2 partial-unique
constraints) and safe to apply while the old code is still live.

## Phase C — deploy code + verify

1. Merge `dev` → `main`; **push from VS Code** (Claude's shell can't auth to GitHub).
   App Platform auto-deploys all 3 components on push to `main`. The push touches
   only code — the **app spec is untouched**, so the SECRET-blanking footgun is not
   in play (never `doctl apps update --spec` here).
2. Watch the deploy go healthy (`/api/health`), then smoke-test prod:
   - `https://corpus.nick.law/browse` → search returns case rows
   - `https://corpus.nick.law/cases/51200` (State v. Plain) renders opinions + body segments

Ordering: migrate is the only hard prerequisite for the new code. Loading the data
before the deploy avoids an empty-caselaw window.

## Rollback

- **DB:** restore `prod_baseline.dump` over prod (full pre-change snapshot), or, since
  the load is purely additive, delete the caselaw rows:
  `DELETE FROM corpus_crossreference WHERE source IN ('caselaw_link','caselaw_graph');`
  `DELETE FROM corpus_reportercitation;`
  `DELETE FROM corpus_nodeversion WHERE node_id IN (SELECT id FROM corpus_node WHERE source_id=4);`
  `DELETE FROM corpus_node WHERE source_id=4;` (then the seed Source/NodeTypes from 0011 are harmless).
- **Code:** App Platform keeps prior deployments — roll back to the last-good in the panel.

## Notes / deferred

- Editions compare ships but prod has no edition rows → shows the graceful
  "only one edition loaded" state. Loading edition data is a separate step.
- Caselaw embeddings are still deferred (Phase 4 / chunking) — search is FTS-only
  for cases; this is unchanged by this deploy.
</content>
