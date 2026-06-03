"""
Source 2 — Generic submissions under review.
Static HTML table, fetched with httpx and parsed with BeautifulSoup.
All columns mapped explicitly from the live page structure.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.cache import cache_get, cache_set
from app.config import GENERIC_SUBS_URL, HTTP_TIMEOUT, USER_AGENT
from app.models import DrugRecord, SourceResult

# Column indices as confirmed from live page inspection (2025-06)
# Table headers: Medicinal Ingredient(s) | Company Name | Therapeutic Area | Year, Month Accepted
_COL_INGREDIENT = 0
_COL_COMPANY = 1
_COL_THERAPEUTIC_AREA = 2
_COL_DATE_ACCEPTED = 3

_RECORD_URL = GENERIC_SUBS_URL


async def _fetch_page() -> str:
    cached = cache_get("generic_subs_page", "html")
    if cached is not None:
        return cached
    async with httpx.AsyncClient() as client:
        r = await client.get(
            GENERIC_SUBS_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        html = r.text
    cache_set("generic_subs_page", "html", html)
    return html


def _parse_table(html: str) -> list[dict]:
    """Parse all rows from the wb-tables on the page."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        if tbody is None:
            continue
        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue
            rows.append(
                {
                    "ingredient": cells[_COL_INGREDIENT].get_text(separator=", ", strip=True),
                    "company": cells[_COL_COMPANY].get_text(strip=True),
                    "therapeutic_area": cells[_COL_THERAPEUTIC_AREA].get_text(strip=True),
                    "date_accepted": cells[_COL_DATE_ACCEPTED].get_text(strip=True),
                }
            )
    return rows


def _matches(row: dict, query: str, field: str) -> bool:
    q = query.strip().lower()
    if field == "ingredient":
        return q in row["ingredient"].lower()
    if field == "company":
        return q in row["company"].lower()
    if field == "brand":
        # Generic submissions table has no brand column; can't match
        return False
    if field == "din":
        return False
    return False


async def search_generic_submissions(
    query: str,
    field: str = "ingredient",
    extra_terms: Optional[list[str]] = None,
) -> SourceResult:
    if field in ("brand", "din"):
        return SourceResult(
            source="GenericSubmissions",
            status="unsupported",
            error_message=f"Generic Submissions table does not support search by '{field}'.",
        )

    try:
        html = await _fetch_page()
    except Exception as e:
        return SourceResult(
            source="GenericSubmissions", status="error", error_message=str(e)
        )

    all_rows = _parse_table(html)
    if not all_rows:
        return SourceResult(
            source="GenericSubmissions",
            status="error",
            error_message="Could not parse table from page — structure may have changed.",
        )

    terms = [query] + (extra_terms or [])
    matched: list[dict] = []
    seen: set[tuple] = set()
    for row in all_rows:
        for term in terms:
            if _matches(row, term, field):
                key = (row["ingredient"], row["company"], row["date_accepted"])
                if key not in seen:
                    seen.add(key)
                    matched.append(row)
                break

    if not matched:
        return SourceResult(source="GenericSubmissions", status="no_results")

    records = [
        DrugRecord(
            source="GenericSubmissions",
            ingredient=r["ingredient"],
            company=r["company"] if r["company"] != "Not available" else None,
            # Ingredient cell may contain multiple ingredients separated by ";" or ","
            all_ingredients=(
                [i.strip() for i in r["ingredient"].split(";") if i.strip()]
                if ";" in r["ingredient"]
                else [r["ingredient"].strip()]
                if r["ingredient"].strip()
                else []
            ),
            status="Under Review",
            record_url=_RECORD_URL,
            source_specific={
                "therapeutic_area": r["therapeutic_area"],
                "date_accepted": r["date_accepted"],
            },
        )
        for r in matched
    ]
    return SourceResult(
        source="GenericSubmissions", status="ok", records=records, count=len(records)
    )
