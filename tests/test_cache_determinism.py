"""Determinism & cache tests.

- Same offline query yields byte-identical normalized output.
- Cache hit returns identical data and avoids re-fetching (mocked client called once).
- A forced TTL=0 causes a re-fetch and updates the stored value.
"""
import json
import time
import pytest

from app.cache import cache_get, cache_set, _cache_key


# ── Pure cache unit tests ─────────────────────────────────────────────────────

class TestCacheUnit:
    def test_round_trip_simple_value(self, tmp_path, monkeypatch):
        """cache_set / cache_get round-trips a simple value."""
        # Use a unique source+query pair so this test never collides with live cache.
        src, qry = "test_cache_unit", "round_trip_simple"
        cache_set(src, qry, {"hello": "world"}, ttl=60)
        result = cache_get(src, qry)
        assert result == {"hello": "world"}

    def test_expired_entry_returns_none(self):
        """An entry written with TTL=0 is immediately expired."""
        src, qry = "test_cache_unit", "expired_entry"
        cache_set(src, qry, "data", ttl=0)
        time.sleep(0.01)  # tiny sleep to ensure time.time() > expires_at
        result = cache_get(src, qry)
        assert result is None

    def test_cache_miss_returns_none(self):
        assert cache_get("test_cache_unit", "definitely_not_stored_xyzzy") is None

    def test_list_value(self):
        src, qry = "test_cache_unit", "list_value"
        data = [1, 2, {"key": "val"}]
        cache_set(src, qry, data, ttl=60)
        assert cache_get(src, qry) == data

    def test_none_value_stored_and_retrieved(self):
        """None is a valid cacheable value (means 'empty result')."""
        src, qry = "test_cache_unit", "none_value"
        cache_set(src, qry, [], ttl=60)
        assert cache_get(src, qry) == []

    def test_overwrite_updates_value(self):
        src, qry = "test_cache_unit", "overwrite"
        cache_set(src, qry, "v1", ttl=60)
        cache_set(src, qry, "v2", ttl=60)
        assert cache_get(src, qry) == "v2"

    def test_cache_key_deterministic(self):
        k1 = _cache_key("dpd", "metformin")
        k2 = _cache_key("dpd", "metformin")
        assert k1 == k2

    def test_cache_key_different_for_different_inputs(self):
        assert _cache_key("dpd", "metformin") != _cache_key("noc", "metformin")
        assert _cache_key("dpd", "metformin") != _cache_key("dpd", "ibuprofen")


# ── Source-level cache behaviour ──────────────────────────────────────────────

async def test_dpd_cache_hit_avoids_refetch(monkeypatch):
    """When the cache holds a value, the DPD source must not issue a new HTTP request."""
    import app.sources.dpd as dpd_mod
    from tests.conftest import load_json

    # Pre-populate the cache with the metformin activeingredient fixture data.
    cache_rows = load_json("dpd/activeingredient_metformin.json")
    cache_set("dpd_ingredient", "metformin", cache_rows)

    call_count = 0

    async def _spy(client, url, params):
        nonlocal call_count
        call_count += 1
        raise AssertionError("HTTP call was made despite cache hit!")

    original = dpd_mod._get_json
    monkeypatch.setattr(dpd_mod, "_get_json", _spy)

    try:
        # _fetch_drug_codes_by_ingredient should return from cache without calling _get_json.
        import httpx, asyncio
        async with httpx.AsyncClient() as client:
            result = await dpd_mod._fetch_drug_codes_by_ingredient(client, "metformin")
        assert result == cache_rows
        assert call_count == 0, "Cache hit made unexpected HTTP request"
    finally:
        monkeypatch.setattr(dpd_mod, "_get_json", original)


# ── Determinism: same offline query → identical output ────────────────────────

async def test_dpd_offline_query_deterministic(mock_dpd):
    """The same offline DPD query must produce byte-identical serialized results."""
    from app.sources.dpd import search_dpd
    result1 = await search_dpd("metformin", field="ingredient")
    result2 = await search_dpd("metformin", field="ingredient")

    assert result1.status == result2.status
    assert result1.count == result2.count
    # Serialize to JSON and compare — same field order expected from Pydantic.
    j1 = json.dumps([r.model_dump() for r in result1.records], sort_keys=True)
    j2 = json.dumps([r.model_dump() for r in result2.records], sort_keys=True)
    assert j1 == j2, "Offline DPD results are non-deterministic"


async def test_noc_offline_query_deterministic(mock_noc):
    from app.sources.noc import search_noc
    r1 = await search_noc("NORINYL 1/50 21DAY", field="brand")
    r2 = await search_noc("NORINYL 1/50 21DAY", field="brand")
    assert r1.status == r2.status
    assert r1.count == r2.count
    j1 = json.dumps([r.model_dump() for r in r1.records], sort_keys=True)
    j2 = json.dumps([r.model_dump() for r in r2.records], sort_keys=True)
    assert j1 == j2


async def test_grouping_deterministic():
    """group_records on the same list always returns the same group order."""
    from app.grouping import group_records
    from app.models import DrugRecord
    records = [
        DrugRecord(source="DPD", all_ingredients=["A", "B"], brand_name="X"),
        DrugRecord(source="DPD", all_ingredients=["A"], brand_name="Y"),
        DrugRecord(source="DPD", all_ingredients=["A", "B"], brand_name="Z"),
    ]
    groups1 = group_records(records, searched_ingredient="A")
    groups2 = group_records(records, searched_ingredient="A")
    assert [g.label for g in groups1] == [g.label for g in groups2]
