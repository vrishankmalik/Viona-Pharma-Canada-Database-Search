#!/usr/bin/env python3
"""Re-record all HTTP fixtures from live government sources.

Run from the project root:
    make refresh-fixtures
    # or
    python3 tests/scripts/refresh_fixtures.py

Requires network access.  Writes fixture files under tests/fixtures/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path.
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from app.config import DPD_BASE, USER_AGENT, HTTP_TIMEOUT, NOC_BASE, GENERIC_SUBS_URL, PATENT_BASE

FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
_HEADERS_JSON = {"User-Agent": USER_AGENT, "Accept": "application/json"}
_HEADERS_HTML = {"User-Agent": USER_AGENT, "Accept": "text/html"}


async def save_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ {path.relative_to(PROJECT_ROOT)}")


async def save_html(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  ✓ {path.relative_to(PROJECT_ROOT)}")


async def refresh_dpd() -> None:
    print("\n── DPD ─────────────────────────────────────────────────────────")
    async with httpx.AsyncClient() as client:
        # Metformin ingredient search
        r = await client.get(f"{DPD_BASE}/activeingredient/",
                             params={"ingredientname": "metformin", "lang": "en", "type": "json"},
                             headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        await save_json(FIXTURES / "dpd" / "activeingredient_metformin.json", rows[:5])

        if rows:
            # Pick the first drug code for per-code fixtures.
            code = rows[0]["drug_code"]
            for endpoint in ("drugproduct", "form", "route", "status", "schedule"):
                r2 = await client.get(f"{DPD_BASE}/{endpoint}/",
                                      params={"id": code, "lang": "en", "type": "json"},
                                      headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
                r2.raise_for_status()
                await save_json(FIXTURES / "dpd" / f"{endpoint}_{code}.json", r2.json())
            r3 = await client.get(f"{DPD_BASE}/activeingredient/",
                                  params={"id": code, "lang": "en", "type": "json"},
                                  headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
            r3.raise_for_status()
            await save_json(FIXTURES / "dpd" / f"activeingredient_code_{code}.json", r3.json())

        # Stable golden DINs.
        for din, code_hint in [("00326925", None), ("00000019", None)]:
            r4 = await client.get(f"{DPD_BASE}/drugproduct/",
                                  params={"din": din, "lang": "en", "type": "json"},
                                  headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
            r4.raise_for_status()
            product = r4.json()
            if isinstance(product, list):
                product = product[0] if product else {}
            dc = product.get("drug_code")
            if dc:
                await save_json(FIXTURES / "dpd" / f"drugproduct_code_{dc}.json", product)
                for ep in ("form", "route", "status", "schedule"):
                    re2 = await client.get(f"{DPD_BASE}/{ep}/",
                                           params={"id": dc, "lang": "en", "type": "json"},
                                           headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
                    re2.raise_for_status()
                    await save_json(FIXTURES / "dpd" / f"{ep}_{dc}.json", re2.json())
                re3 = await client.get(f"{DPD_BASE}/activeingredient/",
                                       params={"id": dc, "lang": "en", "type": "json"},
                                       headers=_HEADERS_JSON, timeout=HTTP_TIMEOUT)
                re3.raise_for_status()
                await save_json(FIXTURES / "dpd" / f"activeingredient_code_{dc}.json", re3.json())


async def refresh_noc() -> None:
    print("\n── NOC ─────────────────────────────────────────────────────────")
    import re as _re
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{NOC_BASE}/?lang=eng",
                             headers=_HEADERS_HTML, timeout=HTTP_TIMEOUT,
                             follow_redirects=True)
        r.raise_for_status()
        await save_html(FIXTURES / "noc" / "csrf_page.html", r.text)
        cookies = dict(r.cookies)
        m = _re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
        csrf = m.group(1) if m else ""

        for brand, fname in [("NORINYL 1/50 21DAY", "results_norinyl.html"),
                              ("Glucophage", "results_glucophage.html")]:
            rp = await client.post(
                f"{NOC_BASE}/doSearch",
                data={"_csrf": csrf, "medicinalIngredient": "", "productName": brand,
                      "din": "", "manufacturer": "", "submissionClass": "0",
                      "therapeuticClass": "", "submissionType": "0", "productType": "0",
                      "nocFromDate": "", "nocToDate": "", "submit": "Search"},
                cookies=cookies,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=HTTP_TIMEOUT, follow_redirects=True,
            )
            rp.raise_for_status()
            await save_html(FIXTURES / "noc" / fname, rp.text)

        # Too-many-records: broad search.
        rp2 = await client.post(
            f"{NOC_BASE}/doSearch",
            data={"_csrf": csrf, "medicinalIngredient": "metformin", "productName": "",
                  "din": "", "manufacturer": "", "submissionClass": "0",
                  "therapeuticClass": "", "submissionType": "0", "productType": "0",
                  "nocFromDate": "", "nocToDate": "", "submit": "Search"},
            cookies=cookies,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=HTTP_TIMEOUT, follow_redirects=True,
        )
        rp2.raise_for_status()
        await save_html(FIXTURES / "noc" / "results_too_many.html", rp2.text)


async def refresh_gsur() -> None:
    print("\n── GSUR ────────────────────────────────────────────────────────")
    async with httpx.AsyncClient() as client:
        r = await client.get(GENERIC_SUBS_URL, headers=_HEADERS_HTML,
                             timeout=HTTP_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        await save_html(FIXTURES / "generic_submissions" / "page.html", r.text)


async def refresh_patent_register() -> None:
    print("\n── Patent Register ─────────────────────────────────────────────")
    async with httpx.AsyncClient(verify=False) as client:  # noqa: S501
        r = await client.get(f"{PATENT_BASE}/index-eng.jsp",
                             headers=_HEADERS_HTML, timeout=HTTP_TIMEOUT,
                             follow_redirects=True)
        r.raise_for_status()
        await save_html(FIXTURES / "patent_register" / "index.html", r.text)
        session = r.cookies.get("JSESSIONID", "")
        rp = await client.post(
            f"{PATENT_BASE}/search",
            data={"medicinalIngredient": "METFORMIN HYDROCHLORIDE", "brandName": "",
                  "patentNumber": "", "din": "", "cspNumber": "", "search": "Search"},
            cookies={"JSESSIONID": session} if session else {},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=HTTP_TIMEOUT, follow_redirects=True,
        )
        rp.raise_for_status()
        await save_html(FIXTURES / "patent_register" / "results_metformin.html", rp.text)


async def main() -> None:
    print("Refreshing fixtures from live sources…")
    await refresh_dpd()
    await refresh_noc()
    await refresh_gsur()
    await refresh_patent_register()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
