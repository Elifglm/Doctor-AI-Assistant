"""ICD-10 search service with Turkish character support."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text

from apps.backend.src.db.icd10_database import icd10_session_maker

logger = logging.getLogger(__name__)

_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")


def normalize_turkish(s: str) -> str:
    """Normalize Turkish characters to ASCII equivalents for search."""
    return s.lower().translate(_TR_MAP)


@dataclass
class ICD10Result:
    icd_kodu: str
    tani: str
    ust_kod: str | None
    seviye: int


class ICD10Service:
    """Search and lookup ICD-10 codes from the local database."""

    async def search(self, query: str, limit: int = 20) -> list[ICD10Result]:
        """Search ICD-10 codes by code prefix or diagnosis text.

        Handles Turkish characters and returns results sorted by relevance.
        Uses multi-word matching to improve precision over single-substring LIKE.
        """
        query = query.strip()
        if not query:
            return []

        normalized = normalize_turkish(query)
        upper_query = query.upper()

        async with icd10_session_maker() as session:
            # Try code prefix match first, then text match
            results: list[ICD10Result] = []
            seen_codes: set[str] = set()

            # 1. Exact code prefix match
            rows = await session.execute(
                text(
                    "SELECT icd_kodu, tani, ust_kod, seviye FROM icd10 "
                    "WHERE icd_kodu LIKE :pattern ORDER BY icd_kodu LIMIT :limit"
                ),
                {"pattern": f"{upper_query}%", "limit": limit},
            )
            for row in rows:
                if row[0] not in seen_codes:
                    seen_codes.add(row[0])
                    results.append(ICD10Result(
                        icd_kodu=row[0], tani=row[1],
                        ust_kod=row[2], seviye=row[3],
                    ))

            # 2. Normalized text search with multi-word matching
            remaining = limit - len(results)
            if remaining > 0:
                # Split query into significant words for better precision
                query_words = [w for w in normalized.split() if len(w) > 2]

                if query_words:
                    # Build a query that requires ALL significant words to appear
                    # This is much stricter than a single LIKE %full_phrase%
                    where_clauses = []
                    params: dict[str, str | int] = {"limit": remaining + 10}
                    for i, word in enumerate(query_words):
                        param_name = f"w{i}"
                        where_clauses.append(f"tani_normalized LIKE :{param_name}")
                        params[param_name] = f"%{word}%"

                    where_sql = " AND ".join(where_clauses)
                    rows = await session.execute(
                        text(
                            f"SELECT icd_kodu, tani, ust_kod, seviye FROM icd10 "
                            f"WHERE {where_sql} "
                            f"ORDER BY seviye ASC, icd_kodu LIMIT :limit"
                        ),
                        params,
                    )
                    for row in rows:
                        if row[0] not in seen_codes:
                            seen_codes.add(row[0])
                            results.append(ICD10Result(
                                icd_kodu=row[0], tani=row[1],
                                ust_kod=row[2], seviye=row[3],
                            ))
                        if len(results) >= limit:
                            break

                # 3. Fallback: if strict multi-word match found nothing,
                # try individual words but fetch more candidates for caller to rank
                if len(results) == 0 and len(query_words) > 1:
                    # Use the longest (most specific) word
                    longest_word = max(query_words, key=len)
                    rows = await session.execute(
                        text(
                            "SELECT icd_kodu, tani, ust_kod, seviye FROM icd10 "
                            "WHERE tani_normalized LIKE :pattern "
                            "ORDER BY seviye ASC, icd_kodu LIMIT :limit"
                        ),
                        {"pattern": f"%{longest_word}%", "limit": remaining + 10},
                    )
                    for row in rows:
                        if row[0] not in seen_codes:
                            seen_codes.add(row[0])
                            results.append(ICD10Result(
                                icd_kodu=row[0], tani=row[1],
                                ust_kod=row[2], seviye=row[3],
                            ))
                        if len(results) >= limit:
                            break

            return results[:limit]

    async def get_by_code(self, code: str) -> ICD10Result | None:
        """Look up a single ICD-10 code."""
        async with icd10_session_maker() as session:
            row = await session.execute(
                text("SELECT icd_kodu, tani, ust_kod, seviye FROM icd10 WHERE icd_kodu = :code"),
                {"code": code.upper().strip()},
            )
            r = row.first()
            if r is None:
                return None
            return ICD10Result(icd_kodu=r[0], tani=r[1], ust_kod=r[2], seviye=r[3])

    async def get_children(self, parent_code: str) -> list[ICD10Result]:
        """Get all subcodes of a parent ICD-10 code."""
        async with icd10_session_maker() as session:
            rows = await session.execute(
                text(
                    "SELECT icd_kodu, tani, ust_kod, seviye FROM icd10 "
                    "WHERE ust_kod = :code ORDER BY icd_kodu"
                ),
                {"code": parent_code.upper().strip()},
            )
            return [
                ICD10Result(icd_kodu=r[0], tani=r[1], ust_kod=r[2], seviye=r[3])
                for r in rows
            ]
