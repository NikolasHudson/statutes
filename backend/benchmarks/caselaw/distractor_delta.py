"""Distractor-delta probe for the adversarial (D) eval pairs.

For each pair, report the case-level rank of BOTH the target and its keyword
distractor under vector / hybrid / vector_rr / hybrid_rr, and whether the
reranker pushed the target above the distractor (the 'delta').
"""

from apps.corpus.models import NodeVersion
from apps.corpus.services.rerank import default_reranker
from apps.corpus.services.search import hybrid_search, vector_search
from apps.corpus.services.voyage import default_client

DEEP = 100
POOL = 20
RERANK_DOC_CHARS = 8000
SRC = "iowa-caselaw"

PAIRS = [
    ("D16  parole release form -> consent to search car trunk",
     "Does signing a parole release form count as voluntary consent to let an officer search your car trunk?",
     ("State v. Baldon", "cl-cluster-4472245"), ("State v. Ochoa", "cl-cluster-4472474")),
    ("D17  warrantless suspicionless search of parolee's HOME",
     "Warrantless suspicionless search of a parolee's home by general police officers under the state constitution.",
     ("State v. Ochoa", "cl-cluster-4472474"), ("State v. Baldon", "cl-cluster-4472245")),
    ("D20  spectator waiver at racetrack pit gate",
     "Spectator liability waiver signed at the entrance gate of a dirt racetrack pit area.",
     ("Huber v. Hovey", "cl-cluster-1309491"), ("Feld v. Borkowski", "cl-cluster-4472505")),
]


def cluster_of(path):
    return path.split("/", 1)[0]


def collapse(pairs, nv2cl):
    seen, out = set(), []
    for nv_id, _ in pairs:
        cl = nv2cl.get(nv_id)
        if cl and cl not in seen:
            seen.add(cl)
            out.append(cl)
    return out


def rank_of(clusters, target):
    return clusters.index(target) + 1 if target in clusters else None


def rr(r):
    return str(r) if r else f">{DEEP}"


client = default_client()
reranker = default_reranker()
client.embed_texts(["warmup"], input_type="query")
vector_search("warmup", limit=1, source_slug=SRC, client=client)  # load pgvector GUC

for title, query, (tname, tcl), (dname, dcl) in PAIRS:
    vec = vector_search(query, limit=DEEP, source_slug=SRC, client=client)
    hyb_objs = hybrid_search(query, limit=DEEP, per_retriever=DEEP, source_slug=SRC, client=client)
    hyb = [(h.node_version_id, h.score) for h in hyb_objs]

    all_ids = {i for i, _ in (*vec, *hyb)}
    nv2cl = {i: cluster_of(p) for i, p in
             NodeVersion.objects.filter(id__in=all_ids).values_list("id", "node__path")}

    def rerank_clusters(hits):
        ids = [i for i, _ in hits[:POOL]]
        texts = {i: f"{(h or '')}\n{(b or '')[:RERANK_DOC_CHARS]}"
                 for i, h, b in NodeVersion.objects.filter(id__in=ids)
                 .values_list("id", "node__heading", "body_text")}
        ranked_ids = reranker.rerank(query, [(i, texts.get(i, "")) for i in ids], top_k=POOL)
        n2c = {i: cluster_of(p) for i, p in
               NodeVersion.objects.filter(id__in=ranked_ids).values_list("id", "node__path")}
        return collapse([(i, 0.0) for i in ranked_ids], n2c)

    configs = {
        "vector":    collapse(vec, nv2cl),
        "hybrid":    collapse(hyb, nv2cl),
        "vector_rr": rerank_clusters(vec),
        "hybrid_rr": rerank_clusters(hyb),
    }

    print("=" * 88)
    print(title)
    print(f'  query: "{query}"')
    print(f"  TARGET = {tname} ({tcl})   |   DISTRACTOR = {dname} ({dcl})")
    print(f'  {"config":11} {"target":>8} {"distract":>9}   verdict')
    for cfg, cls in configs.items():
        tr, dr = rank_of(cls, tcl), rank_of(cls, dcl)
        if tr and (dr is None or tr < dr):
            verdict = "PASS  target outranks distractor"
        elif tr and dr and tr > dr:
            verdict = "FAIL  distractor outranks target"
        elif tr is None:
            verdict = "MISS  target not in top-100"
        else:
            verdict = "?"
        print(f"  {cfg:11} {rr(tr):>8} {rr(dr):>9}   {verdict}")
print("=" * 88)
