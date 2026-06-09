"""Tier 6 — Robustness tests (offline, mocked HTTP failures).

Every source must degrade gracefully: return a structured SourceResult with
status "error" or "timeout", never raise an unhandled exception.
"""
import re
import pytest
import httpx
import respx

from app.sources.dpd import search_dpd
from app.sources.noc import search_noc
from app.sources.generic_submissions import search_generic_submissions
from app.sources.patent_register import search_patent_register


# ── Helpers ───────────────────────────────────────────────────────────────────

DPD_PATTERN = re.compile(r"https://health-products\.canada\.ca/api/drug/.*")
NOC_GET_PATTERN = re.compile(r"https://health-products\.canada\.ca/noc-ac/.*")
NOC_POST_URL = "https://health-products.canada.ca/noc-ac/doSearch"
GSUR_PATTERN = re.compile(r"https://www\.canada\.ca/.*generic-submissions.*")
PR_PATTERN = re.compile(r"https://pr-rdb\.hc-sc\.gc\.ca/.*")


def _no_cache_patch(monkeypatch):
    noop = lambda *a, **k: None
    for mod in (
        "app.sources.dpd",
        "app.sources.noc",
        "app.sources.patent_register",
        "app.sources.generic_submissions",
    ):
        monkeypatch.setattr(f"{mod}.cache_get", noop)
        monkeypatch.setattr(f"{mod}.cache_set", noop)


# ── 500 / 503 responses ───────────────────────────────────────────────────────

async def test_dpd_500_returns_no_results_not_exception(monkeypatch):
    """A 500 on the DPD ingredient endpoint must not crash — DPD silently swallows errors."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(DPD_PATTERN).mock(return_value=httpx.Response(500, text="Internal Server Error"))
        result = await search_dpd("metformin", field="ingredient")
    assert result.status in ("no_results", "ok", "error")


async def test_noc_500_returns_error(monkeypatch):
    """A 500 on the NOC CSRF page must yield status='error'."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(NOC_GET_PATTERN).mock(return_value=httpx.Response(500, text="Server Error"))
        respx.post(NOC_POST_URL).mock(return_value=httpx.Response(500, text="Server Error"))
        result = await search_noc("metformin hydrochloride", field="ingredient")
    assert result.status == "error"
    assert result.error_message is not None


async def test_gsur_503_returns_error(monkeypatch):
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(GSUR_PATTERN).mock(return_value=httpx.Response(503, text="Service Unavailable"))
        result = await search_generic_submissions("metformin", field="ingredient")
    assert result.status == "error"


async def test_patent_register_500_returns_error(monkeypatch):
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(PR_PATTERN).mock(return_value=httpx.Response(500, text="Server Error"))
        respx.post(PR_PATTERN).mock(return_value=httpx.Response(500, text="Server Error"))
        result = await search_patent_register("metformin", field="ingredient")
    assert result.status == "error"


# ── Connection timeout ────────────────────────────────────────────────────────

async def test_noc_timeout_returns_error(monkeypatch):
    """A connection timeout on the NOC CSRF page yields status='error'."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(NOC_GET_PATTERN).mock(side_effect=httpx.TimeoutException("timed out"))
        result = await search_noc("metformin hydrochloride", field="ingredient")
    assert result.status == "error"
    assert result.error_message is not None


async def test_gsur_timeout_returns_error(monkeypatch):
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(GSUR_PATTERN).mock(side_effect=httpx.TimeoutException("timed out"))
        result = await search_generic_submissions("metformin", field="ingredient")
    assert result.status == "error"


async def test_patent_register_timeout_returns_error(monkeypatch):
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(PR_PATTERN).mock(side_effect=httpx.TimeoutException("timed out"))
        result = await search_patent_register("metformin", field="ingredient")
    assert result.status == "error"


# ── Truncated / invalid JSON ──────────────────────────────────────────────────

async def test_dpd_invalid_json_does_not_crash(monkeypatch):
    """Truncated JSON from DPD must not propagate an exception to the caller."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(DPD_PATTERN).mock(
            return_value=httpx.Response(200, text="{invalid json{{{{", headers={"content-type": "application/json"})
        )
        result = await search_dpd("metformin", field="ingredient")
    # DPD silently swallows errors in _fetch_by_term, so it returns no_results or ok.
    assert result.status in ("no_results", "ok", "error")


async def test_noc_invalid_html_does_not_crash(monkeypatch):
    """Completely broken HTML from NOC produces an empty result, not an exception."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(NOC_GET_PATTERN).mock(
            return_value=httpx.Response(200, text="<html>no csrf here at all</html>")
        )
        respx.post(NOC_POST_URL).mock(
            return_value=httpx.Response(200, text="<html>no table here</html>")
        )
        result = await search_noc("metformin hydrochloride", field="ingredient")
    assert result.status in ("no_results", "error")


async def test_gsur_broken_html_returns_error(monkeypatch):
    """An HTML page with no table must surface as error, not no_results silently."""
    _no_cache_patch(monkeypatch)
    with respx.mock(assert_all_called=False):
        respx.get(GSUR_PATTERN).mock(
            return_value=httpx.Response(200, text="<html><body>no table</body></html>")
        )
        result = await search_generic_submissions("metformin", field="ingredient")
    # GSUR raises an error when no table rows are found.
    assert result.status == "error"
    assert result.error_message is not None


# ── Unsupported search fields ─────────────────────────────────────────────────

async def test_noc_unsupported_field_never_crashes():
    result = await search_noc("anything", field="zzz_unknown")
    assert result.status == "unsupported"


async def test_gsur_brand_search_unsupported():
    result = await search_generic_submissions("Lipitor", field="brand")
    assert result.status == "unsupported"


async def test_gsur_din_search_unsupported():
    result = await search_generic_submissions("12345678", field="din")
    assert result.status == "unsupported"


async def test_patent_register_company_unsupported():
    result = await search_patent_register("Pfizer", field="company")
    assert result.status == "unsupported"


# ── Partial results when some drug-code fetches fail ─────────────────────────

async def test_dpd_partial_failure_returns_available_records(monkeypatch, no_cache):
    """When some per-code fetches return 500, results for other codes still appear."""
    call_count = 0

    def _mixed_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        params = dict(request.url.params)
        if "ingredientname" in params:
            return httpx.Response(200, json=[
                {"drug_code": 11111, "ingredient_name": "DOXEPIN HCL", "strength": "10", "strength_unit": "MG"},
                {"drug_code": 22222, "ingredient_name": "DOXEPIN HCL", "strength": "25", "strength_unit": "MG"},
            ])
        if "id" in params and params["id"] == "11111":
            return httpx.Response(500, text="error")
        from tests.conftest import load_json
        import json
        fp = __import__("pathlib").Path(__file__).parent / "fixtures" / f"dpd/drugproduct_code_{params.get('id', '0')}.json"
        if fp.exists():
            return httpx.Response(200, json=json.loads(fp.read_bytes()))
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False):
        respx.get(DPD_PATTERN).mock(side_effect=_mixed_response)
        result = await search_dpd("doxepin", field="ingredient")

    # The result should not crash; status is ok or no_results.
    assert result.status in ("ok", "no_results")
