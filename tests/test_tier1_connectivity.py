"""Tier 1 — Connectivity / smoke tests.

These hit live government endpoints.  They are marked @pytest.mark.integration
and skipped by default (see pytest.ini addopts).  Run with:
    make test-live
"""
import pytest

from app.sources.dpd import search_dpd
from app.sources.generic_submissions import search_generic_submissions
from app.sources.noc import search_noc
from app.sources.patent_register import search_patent_register


@pytest.mark.integration
async def test_dpd_live_smoke():
    """DPD REST API is reachable and returns a parseable payload."""
    result = await search_dpd("metformin hydrochloride", field="ingredient")
    assert result.status in ("ok", "no_results", "error"), result.status
    if result.status == "ok":
        assert result.count > 0
        r = result.records[0]
        assert r.source == "DPD"
        assert r.din is not None
        assert r.brand_name is not None


@pytest.mark.integration
async def test_noc_live_smoke():
    """NOC search endpoint is reachable and returns a parseable payload."""
    result = await search_noc("Glucophage", field="brand")
    assert result.status in ("ok", "no_results", "error"), result.status
    if result.status == "ok":
        assert result.count > 0
        r = result.records[0]
        assert r.source == "NOC"
        assert r.record_url is not None


@pytest.mark.integration
async def test_gsur_live_smoke():
    """Generic Submissions HTML page is reachable and table-parseable."""
    result = await search_generic_submissions("metformin", field="ingredient")
    assert result.status in ("ok", "no_results", "error"), result.status
    if result.status == "ok":
        assert result.count > 0
        r = result.records[0]
        assert r.source == "GenericSubmissions"
        assert r.ingredient is not None


@pytest.mark.integration
async def test_patent_register_live_smoke():
    """Patent Register index page and search are reachable."""
    result = await search_patent_register("metformin", field="ingredient")
    assert result.status in ("ok", "no_results", "error"), result.status
    if result.status == "ok":
        assert result.count > 0
        r = result.records[0]
        assert r.source == "PatentRegister"
        assert r.ingredient is not None
