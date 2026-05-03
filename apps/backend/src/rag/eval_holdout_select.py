"""Carve out a fixed eval hold-out set from ic_anamnez_filt_v1_clean.

Random sample of N rows (default 100) with fixed seed 42 for reproducibility.
The hold-out is moved to a separate table; the embedding corpus
(ic_anamnez_filt_v1_corpus) excludes them so retrieval can never return
the gold reference. Same hold-out applies across all ablation configs
(baseline, format A, metadata B).

Output:
- ic_anamnez_eval_holdout    (N rows, query side of leave-one-out eval)
- ic_anamnez_filt_v1_corpus  (clean rows minus holdout, embedded by build script)
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source", default="ic_anamnez_filt_v1_clean")
    parser.add_argument("--holdout", default="ic_anamnez_eval_holdout")
    parser.add_argument("--corpus", default="ic_anamnez_filt_v1_corpus")
    args = parser.parse_args()

    if not _DB_PATH.exists():
        print(f"DB not found: {_DB_PATH}", file=sys.stderr)
        return 1

    rnd = random.Random(args.seed)

    with sqlite3.connect(_DB_PATH) as conn:
        rowids = [r[0] for r in conn.execute(f'SELECT rowid FROM "{args.source}" ORDER BY rowid')]
        n_total = len(rowids)
        print(f"[holdout] source={args.source}  total={n_total:,}", flush=True)

        if args.n >= n_total:
            print(f"[ERROR] n ({args.n}) >= total ({n_total})", file=sys.stderr)
            return 1

        rnd.shuffle(rowids)
        holdout_rowids = sorted(rowids[: args.n])
        corpus_rowids = sorted(rowids[args.n :])

        cur = conn.cursor()
        for table in (args.holdout, args.corpus):
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')
            cur.execute(f'CREATE TABLE "{table}" AS SELECT * FROM "{args.source}" WHERE 0')

        def insert_chunk(target: str, ids: list[int]) -> None:
            BATCH = 500
            for i in range(0, len(ids), BATCH):
                chunk = ids[i : i + BATCH]
                placeholders = ",".join("?" * len(chunk))
                cur.execute(
                    f'INSERT INTO "{target}" '
                    f'SELECT * FROM "{args.source}" WHERE rowid IN ({placeholders})',
                    chunk,
                )

        insert_chunk(args.holdout, holdout_rowids)
        insert_chunk(args.corpus, corpus_rowids)

        for table in (args.holdout, args.corpus):
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{table}_form_id '
                f'ON "{table}"(FORM_ID)'
            )

        conn.commit()

        n_h = conn.execute(f'SELECT COUNT(*) FROM "{args.holdout}"').fetchone()[0]
        n_c = conn.execute(f'SELECT COUNT(*) FROM "{args.corpus}"').fetchone()[0]
        print(f"[holdout] {args.holdout}: {n_h:,} rows  (seed={args.seed})", flush=True)
        print(f"[holdout] {args.corpus}: {n_c:,} rows", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
