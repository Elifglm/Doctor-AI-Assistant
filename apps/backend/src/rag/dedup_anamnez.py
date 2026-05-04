"""MinHash LSH fuzzy deduplication over ic_anamnez_filt_v1_minimal.

Catches near-duplicate boilerplate cascades (e.g. same templated muayene
across reports) that exact dedup misses. Tokenizes the concatenated
yakinma+oyku+muayene text into 5-shingles, signs with 128 permutations,
and groups via LSH at Jaccard threshold 0.85.

For each duplicate cluster, keeps the FORM_ID with the longest combined
text (most informative variant) and marks the rest as duplicates.

Output: ic_anamnez_filt_v1_clean (subset of v1_minimal with kept rows only).

Usage:
    python -m apps.backend.src.rag.dedup_anamnez [--threshold 0.85]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

from datasketch import MinHash, MinHashLSH

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"

_NUM_PERM = 128
_SHINGLE_K = 5

_TR_LOWER = str.maketrans("ÇĞİÖŞÜI", "çğiöşüı")
_WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+|\d+")


def normalize(text: str) -> str:
    return text.translate(_TR_LOWER).lower()


def shingles(text: str, k: int = _SHINGLE_K) -> set[str]:
    """Word-level k-shingles from normalized text."""
    if not text:
        return set()
    tokens = _WORD_RE.findall(normalize(text))
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def make_minhash(tokens: set[str]) -> MinHash:
    m = MinHash(num_perm=_NUM_PERM)
    for tok in tokens:
        m.update(tok.encode("utf-8"))
    return m


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--source", default="ic_anamnez_filt_v1_minimal")
    parser.add_argument("--output", default="ic_anamnez_filt_v1_clean")
    args = parser.parse_args()

    if not _DB_PATH.exists():
        print(f"DB not found: {_DB_PATH}", file=sys.stderr)
        return 1

    with sqlite3.connect(_DB_PATH) as conn:
        n_src = conn.execute(f'SELECT COUNT(*) FROM "{args.source}"').fetchone()[0]
        print(f"[dedup] source={args.source}  rows={n_src:,}", flush=True)
        print(f"[dedup] threshold={args.threshold}  num_perm={_NUM_PERM}  shingle_k={_SHINGLE_K}", flush=True)

        rows = conn.execute(
            f'SELECT rowid, FORM_ID, COALESCE(yakinma, \'\'), COALESCE(oyku, \'\'), COALESCE(muayene, \'\') '
            f'FROM "{args.source}"'
        ).fetchall()

        t0 = time.perf_counter()
        lsh = MinHashLSH(threshold=args.threshold, num_perm=_NUM_PERM)
        # Use row index as LSH key (FORM_IDs are not unique in source table)
        signatures: dict[int, MinHash] = {}
        text_lens: dict[int, int] = {}
        idx_to_rowid: dict[int, int] = {}

        for i, (rowid, form_id, yak, oyk, muay) in enumerate(rows):
            if i and i % 2500 == 0:
                print(f"  hashing {i:>6,d}/{n_src:,} ({time.perf_counter()-t0:.1f}s)", flush=True)
            combined = f"{yak} {oyk} {muay}".strip()
            sigs = shingles(combined)
            mh = make_minhash(sigs) if sigs else MinHash(num_perm=_NUM_PERM)
            signatures[i] = mh
            text_lens[i] = len(combined)
            idx_to_rowid[i] = rowid
            lsh.insert(str(i), mh)

        print(f"[dedup] hashing done in {time.perf_counter()-t0:.1f}s", flush=True)

        # Cluster: union-find over near-duplicate pairs (over row indices)
        parent = {idx: idx for idx in signatures}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        t1 = time.perf_counter()
        n_pairs = 0
        for idx, mh in signatures.items():
            neighbors = lsh.query(mh)
            for nb in neighbors:
                nb_idx = int(nb)
                if nb_idx != idx:
                    union(idx, nb_idx)
                    n_pairs += 1

        # Per cluster, keep the longest-text member
        clusters: dict[int, list[int]] = {}
        for idx in signatures:
            root = find(idx)
            clusters.setdefault(root, []).append(idx)

        keep_idx: set[int] = set()
        for root, members in clusters.items():
            best = max(members, key=lambda i: text_lens[i])
            keep_idx.add(best)
        keep_rowids: set[int] = {idx_to_rowid[i] for i in keep_idx}

        n_clusters_with_dups = sum(1 for m in clusters.values() if len(m) > 1)
        n_kept = len(keep_rowids)
        n_dropped = n_src - n_kept
        pct = 100 * n_dropped / n_src if n_src else 0.0
        print(
            f"[dedup] clustering done in {time.perf_counter()-t1:.1f}s  "
            f"pairs={n_pairs:,}  clusters_with_dups={n_clusters_with_dups:,}",
            flush=True,
        )
        print(f"[dedup] kept={n_kept:,}  dropped={n_dropped:,} ({pct:.1f}%)", flush=True)

        # Write output table
        cur = conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{args.output}"')
        cur.execute(f'CREATE TABLE "{args.output}" AS SELECT * FROM "{args.source}" WHERE 0')

        keep_list = list(keep_rowids)
        BATCH = 500
        for i in range(0, len(keep_list), BATCH):
            chunk = keep_list[i : i + BATCH]
            placeholders = ",".join("?" * len(chunk))
            cur.execute(
                f'INSERT INTO "{args.output}" '
                f'SELECT * FROM "{args.source}" WHERE rowid IN ({placeholders})',
                chunk,
            )
        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_{args.output}_form_id '
            f'ON "{args.output}"(FORM_ID)'
        )
        conn.commit()
        n_out = conn.execute(f'SELECT COUNT(*) FROM "{args.output}"').fetchone()[0]
        print(f"[dedup] wrote {n_out:,} rows to {args.output}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
