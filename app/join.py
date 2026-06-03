"""Cross-source join of DrugRecords by normalized DIN.

Produces MasterRow objects that carry aligned DPD + NOC + GSUR blocks.
Rows with no DIN are kept as standalone entries with match_method="no_din"
so they are never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.din_utils import normalize_din
from app.models import DrugRecord


@dataclass
class MasterRow:
    din: str  # normalized 8-digit DIN, or "" for DIN-less rows
    dpd_record: Optional[DrugRecord] = None
    noc_records: list[DrugRecord] = field(default_factory=list)
    gsur_records: list[DrugRecord] = field(default_factory=list)

    @property
    def noc_count(self) -> int:
        return len(self.noc_records)

    @property
    def latest_noc_date(self) -> Optional[str]:
        dates = [
            r.source_specific.get("noc_date", "")
            for r in self.noc_records
            if r.source_specific.get("noc_date")
        ]
        return max(dates) if dates else None

    @property
    def all_noc_dates(self) -> list[str]:
        return sorted(
            r.source_specific.get("noc_date", "")
            for r in self.noc_records
            if r.source_specific.get("noc_date")
        )

    @property
    def match_method(self) -> str:
        if not self.din:
            return "no_din"
        sources = set()
        if self.dpd_record:
            sources.add("DPD")
        if self.noc_records:
            sources.add("NOC")
        if self.gsur_records:
            sources.add("GSUR")
        if len(sources) > 1:
            return "exact_din"
        return "partial"


def join_by_din(records: list[DrugRecord]) -> list[MasterRow]:
    """Group DrugRecords from any source into MasterRows keyed by normalized DIN.

    Records with no DIN are appended at the end as standalone rows
    (match_method="no_din") — they are never dropped or merged.
    """
    din_map: dict[str, MasterRow] = {}
    din_less: list[MasterRow] = []

    for record in records:
        raw_din = record.din or ""
        normalized = normalize_din(raw_din) if raw_din else None

        if not normalized:
            row = MasterRow(din="")
            if record.source == "DPD":
                row.dpd_record = record
            elif record.source == "NOC":
                row.noc_records.append(record)
            elif record.source == "GenericSubmissions":
                row.gsur_records.append(record)
            din_less.append(row)
            continue

        if normalized not in din_map:
            din_map[normalized] = MasterRow(din=normalized)
        master = din_map[normalized]

        if record.source == "DPD":
            master.dpd_record = record
        elif record.source == "NOC":
            master.noc_records.append(record)
        elif record.source == "GenericSubmissions":
            master.gsur_records.append(record)

    return list(din_map.values()) + din_less
