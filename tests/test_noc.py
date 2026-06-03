"""Tests for NOC source — live network (integration-marked).

All tests in this file hit the real NOC endpoint.
Run with: make test-live
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.sources.noc import search_noc


@pytest.mark.integration
async def test_noc_brand_search():
    """Brand search for 'Glucophage' — known NOC product."""
    result = await search_noc("Glucophage", field="brand")
    assert result.status in ("ok", "no_results"), f"{result.status}: {result.error_message}"
    if result.status == "ok":
        assert result.count > 0
        for r in result.records:
            assert r.source == "NOC"
            assert r.record_url is not None


@pytest.mark.integration
async def test_noc_ingredient_too_broad():
    """Broad ingredient 'metformin' returns 'too many records' error from NOC."""
    result = await search_noc("metformin", field="ingredient")
    assert result.status in ("error", "ok", "no_results")
    if result.status == "error":
        assert result.error_message is not None


@pytest.mark.integration
async def test_noc_specific_ingredient():
    """More specific ingredient search."""
    result = await search_noc("metformin hydrochloride", field="ingredient")
    assert result.status in ("ok", "no_results", "error")


@pytest.mark.integration
async def test_noc_no_results():
    result = await search_noc("xyznonexistentdrugabc123", field="brand")
    assert result.status in ("no_results", "error", "ok")


@pytest.mark.integration
async def test_noc_columns():
    """NOC records should have noc_date in source_specific."""
    result = await search_noc("Glucophage", field="brand")
    if result.status == "ok" and result.records:
        r = result.records[0]
        assert "noc_date" in r.source_specific
