"""Grouping of DrugRecords by full active-ingredient combination."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.models import DrugRecord

log = logging.getLogger(__name__)

COMBINATION_SEPARATOR = " + "
UNKNOWN_GROUP = "UNKNOWN / UNPARSED"


def _normalize_name(name: str) -> str:
    """Strip, uppercase, collapse internal whitespace; remove trailing separator artifacts (, ;)."""
    return re.sub(r"\s+", " ", name.strip(" ,;")).upper()


def _parse_ingredient_string(s: str) -> list[str]:
    """Split a semicolon-delimited ingredient string into normalized names."""
    if not s or not s.strip():
        return []
    parts = re.split(r"\s*;\s*", s)
    return [_normalize_name(p) for p in parts if p.strip()]


def make_combination_key(record: DrugRecord) -> tuple[str, ...]:
    """
    Return a sorted deduplicated tuple of normalized ingredient names.
    {A, B} and {B, A} produce the same key so they collapse into one group.
    """
    if record.all_ingredients:
        names = [_normalize_name(n) for n in record.all_ingredients if n.strip()]
    elif record.ingredient:
        names = _parse_ingredient_string(record.ingredient)
    else:
        return ()
    return tuple(sorted(set(names)))


def combination_label(key: tuple[str, ...]) -> str:
    if not key:
        return UNKNOWN_GROUP
    return COMBINATION_SEPARATOR.join(key)


@dataclass
class CombinationGroup:
    key: tuple[str, ...]
    label: str
    records: list[DrugRecord] = field(default_factory=list)

    @property
    def product_count(self) -> int:
        return len(self.records)

    @property
    def company_count(self) -> int:
        return len({r.company for r in self.records if r.company})

    @property
    def companies(self) -> list[str]:
        return sorted({r.company for r in self.records if r.company})


def group_records(
    records: list[DrugRecord],
    searched_ingredient: Optional[str] = None,
) -> list[CombinationGroup]:
    """
    Group records by full active-ingredient combination and sort them.

    Ordering:
    - Exact single-ingredient match (when searched_ingredient is provided) first
    - Then descending product count, ties broken alphabetically by label
    """
    groups: dict[tuple[str, ...], CombinationGroup] = {}

    for record in records:
        key = make_combination_key(record)
        if not key:
            key = (UNKNOWN_GROUP,)
            log.warning(
                "No parseable ingredients: source=%s brand=%s din=%s",
                record.source,
                record.brand_name,
                record.din,
            )
        if key not in groups:
            groups[key] = CombinationGroup(key=key, label=combination_label(key))
        groups[key].records.append(record)

    exact_key = (_normalize_name(searched_ingredient),) if searched_ingredient else None

    def sort_key(g: CombinationGroup) -> tuple:
        is_exact = exact_key is not None and g.key == exact_key
        return (0 if is_exact else 1, -g.product_count, g.label)

    return sorted(groups.values(), key=sort_key)
