"""
Source 3 — Notice of Compliance (NOC / NOC with conditions).
Form-based POST to health-products.canada.ca/noc-ac/doSearch.
CSRF token and session cookie are fetched fresh per request.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.cache import cache_get, cache_set
from app.config import HTTP_TIMEOUT, NOC_BASE, USER_AGENT
from app.models import DrugRecord, SourceResult

_SEARCH_URL = f"{NOC_BASE}/doSearch"
_DETAIL_BASE = f"{NOC_BASE}/nocInfo"
_LANG_URL = f"{NOC_BASE}/?lang=eng"


async def _get_csrf_and_cookies() -> tuple[str, dict]:
    """Return (csrf_token, cookies_dict) from the search form page."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            _LANG_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        html = r.text
        cookies = dict(r.cookies)

    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    return csrf, cookies


def _parse_results_table(html: str) -> list[dict]:
    """
    Parse the NOC results table.
    Columns (confirmed live): Product(s) | Manufacturer | Published Notes | NOC Date | Medicinal ingredient(s) | DIN(s)
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 6:
            continue

        # Product(s) — may contain an <a> with detail link
        product_cell = cells[0]
        links = product_cell.find_all("a")
        product_names = [a.get_text(strip=True) for a in links] or [product_cell.get_text(strip=True)]
        # Extract the record URL from the first link
        href = links[0]["href"] if links else None
        record_url = (
            f"https://health-products.canada.ca{href}" if href and href.startswith("/") else href
        )

        manufacturer = cells[1].get_text(strip=True)
        published_notes = cells[2].get_text(strip=True)  # NOC/c marker
        noc_date = cells[3].get_text(strip=True)
        ingredients = cells[4].get_text(separator="; ", strip=True)
        dins_raw = cells[5].get_text(separator="; ", strip=True)
        dins = dins_raw if dins_raw.lower() not in ("not applicable", "") else None

        rows.append(
            {
                "products": ", ".join(product_names),
                "manufacturer": manufacturer,
                "published_notes": published_notes,
                "noc_date": noc_date,
                "ingredients": ingredients,
                "dins": dins,
                "record_url": record_url,
                "noc_with_conditions": bool(published_notes.strip()),
            }
        )
    return rows


async def _do_search(form_data: dict, cookies: dict) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            _SEARCH_URL,
            data=form_data,
            cookies=cookies,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": _LANG_URL,
            },
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.text


async def search_noc(
    query: str,
    field: str = "ingredient",
    extra_terms: Optional[list[str]] = None,
) -> SourceResult:
    terms = [query] + (extra_terms or [])

    # Map our field names to NOC form fields
    field_map = {
        "ingredient": "medicinalIngredient",
        "brand": "productName",
        "company": "manufacturer",
        "din": "din",
    }
    noc_field = field_map.get(field)
    if noc_field is None:
        return SourceResult(
            source="NOC",
            status="unsupported",
            error_message=f"NOC does not support search by '{field}'.",
        )

    all_rows: list[dict] = []
    seen_keys: set[tuple] = set()

    for term in terms:
        cache_key = f"noc_{field}:{term.lower()}"
        cached = cache_get("noc", cache_key)
        if cached is not None:
            rows = cached
        else:
            try:
                csrf, cookies = await _get_csrf_and_cookies()
                form_data = {
                    "_csrf": csrf,
                    "medicinalIngredient": "",
                    "productName": "",
                    "din": "",
                    "manufacturer": "",
                    "submissionClass": "0",
                    "therapeuticClass": "",
                    "submissionType": "0",
                    "productType": "0",
                    "nocFromDate": "",
                    "nocToDate": "",
                    "submit": "Search",
                    noc_field: term,
                }
                html = await _do_search(form_data, cookies)

                # Check for "too many records" error
                if "too many records" in html.lower():
                    return SourceResult(
                        source="NOC",
                        status="error",
                        error_message=(
                            "Too many results — please use a more specific search term. "
                            "NOC requires fairly specific ingredient names."
                        ),
                    )
                if "no results" in html.lower() or "Please enter at least one search" in html:
                    rows = []
                else:
                    rows = _parse_results_table(html)

                cache_set("noc", cache_key, rows)
            except Exception as e:
                return SourceResult(source="NOC", status="error", error_message=str(e))

        for row in rows:
            key = (row["products"], row["noc_date"], row["manufacturer"])
            if key not in seen_keys:
                seen_keys.add(key)
                all_rows.append(row)

    if not all_rows:
        return SourceResult(source="NOC", status="no_results")

    records = [
        DrugRecord(
            source="NOC",
            ingredient=r["ingredients"] or None,
            brand_name=r["products"] or None,
            company=r["manufacturer"] or None,
            din=r["dins"],
            all_ingredients=[
                i.strip()
                for i in r["ingredients"].split(";")
                if i.strip()
            ] if r["ingredients"] else [],
            status="NOC/c" if r["noc_with_conditions"] else "NOC",
            record_url=r["record_url"],
            source_specific={
                "noc_date": r["noc_date"],
                "published_notes": r["published_notes"],
            },
        )
        for r in all_rows
    ]
    return SourceResult(source="NOC", status="ok", records=records, count=len(records))
