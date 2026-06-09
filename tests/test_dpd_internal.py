"""Targeted tests for internal DPD module branches not reached by fixture-level tests.

All use monkeypatch to avoid any network or respx complexity.
"""
from __future__ import annotations

import asyncio
import pytest
import httpx

import app.sources.dpd as dpd_mod
from app.sources.dpd import search_dpd, _search_by_din
from app.models import DrugRecord
from tests.conftest import load_json


# ── Shared async stubs ────────────────────────────────────────────────────────

async def _build_stub(client, sem, drug_code, ingredient_rows) -> DrugRecord:
    return DrugRecord(
        source="DPD", brand_name="GLUCOPHAGE", din="02229895",
        company="SANOFI-AVENTIS CANADA INC", all_ingredients=["METFORMIN HYDROCHLORIDE"],
    )


async def _build_stub_none(client, sem, drug_code, ingredient_rows):
    return None


# ── Brand search path (lines 322-327) ────────────────────────────────────────

async def test_dpd_brand_search_code_extraction(no_cache, monkeypatch):
    """Brand search extracts drug_code from product list and builds records."""
    async def _fake_brand(client, brand):
        return [{"drug_code": 99999}]

    monkeypatch.setattr(dpd_mod, "_fetch_drug_codes_by_brand", _fake_brand)
    monkeypatch.setattr(dpd_mod, "_build_record_for_code", _build_stub)

    result = await search_dpd("GLUCOPHAGE", field="brand")
    assert result.status == "ok"
    assert result.count == 1


async def test_dpd_brand_search_no_drug_code_in_product(no_cache, monkeypatch):
    """Products without 'drug_code' key must be silently skipped (no crash)."""
    async def _fake_brand(client, brand):
        return [{"not_drug_code": 1}]

    monkeypatch.setattr(dpd_mod, "_fetch_drug_codes_by_brand", _fake_brand)
    result = await search_dpd("ANYNAME", field="brand")
    assert result.status == "no_results"


# ── Company search path (lines 329-333) ──────────────────────────────────────

async def test_dpd_company_search_code_extraction(no_cache, monkeypatch):
    """Company search extracts drug_code from product list and builds records."""
    async def _fake_company(client, company):
        return [{"drug_code": 99999}]

    monkeypatch.setattr(dpd_mod, "_fetch_drug_codes_by_company", _fake_company)
    monkeypatch.setattr(dpd_mod, "_build_record_for_code", _build_stub)

    result = await search_dpd("SANOFI", field="company")
    assert result.status == "ok"
    assert result.count == 1


# ── _search_by_din cache-hit path (line 376) ─────────────────────────────────

async def test_search_by_din_cache_hit(monkeypatch):
    """When the DIN lookup is cached, skip the HTTP call."""
    prod = load_json("dpd/drugproduct_code_99999.json")

    def _fake_cache_get(src, key):
        if "dpd_din" in src:
            return prod
        return None

    monkeypatch.setattr(dpd_mod, "cache_get", _fake_cache_get)
    monkeypatch.setattr(dpd_mod, "cache_set", lambda *a: None)
    monkeypatch.setattr(dpd_mod, "_build_record_for_code", _build_stub)

    result = await _search_by_din("02229895")
    assert result.status in ("ok", "no_results")


# ── _search_by_din exception path (lines 386-388) ────────────────────────────

async def test_search_by_din_network_error(no_cache, monkeypatch):
    """A network failure during DIN lookup returns status='error'."""
    async def _raise(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    result = await _search_by_din("02229895")
    assert result.status == "error"
    assert result.error_message is not None


# ── _search_by_din empty-response paths (lines 397, 401) ─────────────────────

async def test_search_by_din_empty_dict_response(no_cache, monkeypatch):
    """An empty dict {} from DIN lookup → no_results."""
    async def _empty(*a, **k):
        return {}

    monkeypatch.setattr(dpd_mod, "_get_json", _empty)
    result = await _search_by_din("02229895")
    assert result.status == "no_results"


async def test_search_by_din_product_without_drug_code(no_cache, monkeypatch):
    """A product dict missing 'drug_code' → no_results."""
    async def _no_code(*a, **k):
        return {"brand_name": "X"}

    monkeypatch.setattr(dpd_mod, "_get_json", _no_code)
    result = await _search_by_din("02229895")
    assert result.status == "no_results"


# ── _search_by_din record=None path (line 408) ───────────────────────────────

async def test_search_by_din_build_record_returns_none(no_cache, monkeypatch):
    """When _build_record_for_code returns None → no_results."""
    prod = load_json("dpd/drugproduct_code_99999.json")

    async def _get(*a, **k):
        return prod

    monkeypatch.setattr(dpd_mod, "_get_json", _get)
    monkeypatch.setattr(dpd_mod, "_build_record_for_code", _build_stub_none)
    result = await _search_by_din("02229895")
    assert result.status == "no_results"


# ── _fetch_form / route / schedule exception swallowing ───────────────────────

async def test_fetch_form_exception_returns_empty(no_cache, monkeypatch):
    async def _raise(*a, **k):
        raise httpx.NetworkError("gone")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    async with httpx.AsyncClient() as client:
        form = await dpd_mod._fetch_form(client, asyncio.Semaphore(1), 99999)
    assert form == []


async def test_fetch_route_exception_returns_empty(no_cache, monkeypatch):
    async def _raise(*a, **k):
        raise httpx.NetworkError("gone")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    async with httpx.AsyncClient() as client:
        route = await dpd_mod._fetch_route(client, asyncio.Semaphore(1), 99999)
    assert route == []


async def test_fetch_status_exception_returns_empty(no_cache, monkeypatch):
    async def _raise(*a, **k):
        raise httpx.NetworkError("gone")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    async with httpx.AsyncClient() as client:
        status = await dpd_mod._fetch_status(client, asyncio.Semaphore(1), 99999)
    assert status == []


async def test_fetch_schedule_exception_returns_empty(no_cache, monkeypatch):
    async def _raise(*a, **k):
        raise httpx.NetworkError("gone")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    async with httpx.AsyncClient() as client:
        sched = await dpd_mod._fetch_schedule(client, asyncio.Semaphore(1), 99999)
    assert sched == []


async def test_fetch_ingredients_by_code_exception_returns_empty(no_cache, monkeypatch):
    async def _raise(*a, **k):
        raise httpx.NetworkError("gone")

    monkeypatch.setattr(dpd_mod, "_get_json", _raise)
    async with httpx.AsyncClient() as client:
        ings = await dpd_mod._fetch_ingredients_by_code(client, asyncio.Semaphore(1), 99999)
    assert ings == []


# ── _fetch_status list-vs-dict handling ──────────────────────────────────────

async def test_fetch_status_dict_response(no_cache, monkeypatch):
    """_fetch_status wraps a single-dict response into a list."""
    status_data = {"status": "Marketed", "drug_code": 99999}

    async def _fake(*a, **k):
        return status_data

    monkeypatch.setattr(dpd_mod, "_get_json", _fake)
    async with httpx.AsyncClient() as client:
        result = await dpd_mod._fetch_status(client, asyncio.Semaphore(1), 99999)
    assert result == [status_data]


async def test_fetch_status_list_response(no_cache, monkeypatch):
    """_fetch_status passes a list response through unchanged."""
    status_list = [{"status": "Marketed"}]

    async def _fake(*a, **k):
        return status_list

    monkeypatch.setattr(dpd_mod, "_get_json", _fake)
    async with httpx.AsyncClient() as client:
        result = await dpd_mod._fetch_status(client, asyncio.Semaphore(1), 99999)
    assert result == status_list


# ── _fetch_drugproduct list-vs-dict handling ──────────────────────────────────

async def test_fetch_drugproduct_list_response(no_cache, monkeypatch):
    """_fetch_drugproduct takes data[0] when the API returns a list."""
    prod = load_json("dpd/drugproduct_code_99999.json")

    async def _fake(*a, **k):
        return [prod]

    monkeypatch.setattr(dpd_mod, "_get_json", _fake)
    async with httpx.AsyncClient() as client:
        result = await dpd_mod._fetch_drugproduct(client, asyncio.Semaphore(1), 99999)
    assert result == prod
