"""SUT tetkik search service with Turkish character support."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text

from apps.backend.src.db.sut_database import sut_session_maker

logger = logging.getLogger(__name__)

_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")


def normalize_turkish(s: str) -> str:
    """Normalize Turkish characters to ASCII equivalents for search."""
    return s.lower().translate(_TR_MAP)


@dataclass
class SUTResult:
    kodu: str
    adi: str
    brans: str
    ana_kategori: str
    alt_kategori: str
    puan: float


class SUTService:
    """Search and lookup SUT tetkik codes from the local database."""

    async def search(
        self, query: str, limit: int = 20, brans: str | None = None
    ) -> list[SUTResult]:
        """Search SUT tetkik codes by code prefix or name text."""
        query = query.strip()
        if not query:
            return []

        normalized = normalize_turkish(query)
        upper_query = query.upper()

        async with sut_session_maker() as session:
            results: list[SUTResult] = []
            seen_codes: set[str] = set()

            brans_filter = ""
            params: dict = {"limit": limit}
            if brans:
                brans_filter = " AND brans = :brans"
                params["brans"] = brans.lower()

            # 1. Exact code prefix match
            rows = await session.execute(
                text(
                    f"SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan FROM sut_tetkik "
                    f"WHERE kodu LIKE :pattern{brans_filter} ORDER BY kodu LIMIT :limit"
                ),
                {**params, "pattern": f"{upper_query}%"},
            )
            for row in rows:
                if row[0] not in seen_codes:
                    seen_codes.add(row[0])
                    results.append(SUTResult(
                        kodu=row[0], adi=row[1], brans=row[2],
                        ana_kategori=row[3] or "", alt_kategori=row[4] or "",
                        puan=row[5] or 0.0,
                    ))

            # 2. Normalized text search with multi-word matching
            remaining = limit - len(results)
            if remaining > 0:
                query_words = [w for w in normalized.split() if len(w) > 2]

                if query_words:
                    where_clauses = []
                    word_params: dict = {"limit": remaining + 10}
                    if brans:
                        word_params["brans"] = brans.lower()
                    for i, word in enumerate(query_words):
                        param_name = f"w{i}"
                        where_clauses.append(f"adi_normalized LIKE :{param_name}")
                        word_params[param_name] = f"%{word}%"

                    where_sql = " AND ".join(where_clauses)
                    rows = await session.execute(
                        text(
                            f"SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan FROM sut_tetkik "
                            f"WHERE {where_sql}{brans_filter} "
                            f"ORDER BY kodu LIMIT :limit"
                        ),
                        word_params,
                    )
                    for row in rows:
                        if row[0] not in seen_codes:
                            seen_codes.add(row[0])
                            results.append(SUTResult(
                                kodu=row[0], adi=row[1], brans=row[2],
                                ana_kategori=row[3] or "", alt_kategori=row[4] or "",
                                puan=row[5] or 0.0,
                            ))
                        if len(results) >= limit:
                            break

            return results[:limit]

    async def get_by_code(self, code: str) -> SUTResult | None:
        """Look up a single SUT tetkik code."""
        async with sut_session_maker() as session:
            row = await session.execute(
                text(
                    "SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan "
                    "FROM sut_tetkik WHERE kodu = :code"
                ),
                {"code": code.strip()},
            )
            r = row.first()
            if r is None:
                return None
            return SUTResult(
                kodu=r[0], adi=r[1], brans=r[2],
                ana_kategori=r[3] or "", alt_kategori=r[4] or "",
                puan=r[5] or 0.0,
            )
