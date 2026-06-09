from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class DrugRecord(BaseModel):
    source: str  # "DPD" | "GenericSubmissions" | "NOC" | "PatentRegister"
    ingredient: Optional[str] = None
    brand_name: Optional[str] = None
    company: Optional[str] = None
    din: Optional[str] = None
    strength: Optional[str] = None
    dosage_form: Optional[str] = None
    route: Optional[str] = None
    status: Optional[str] = None
    record_url: Optional[str] = None
    # Full list of active ingredient names (no strength/unit) — used for grouping.
    # Populated at the source level; empty list means grouping falls back to parsing `ingredient`.
    all_ingredients: list[str] = Field(default_factory=list)
    source_specific: dict[str, Any] = Field(default_factory=dict)


class SourceResult(BaseModel):
    source: str
    status: str  # "ok" | "no_results" | "error" | "timeout" | "unsupported"
    records: list[DrugRecord] = Field(default_factory=list)
    error_message: Optional[str] = None
    count: int = 0
    # Populated by DPD when result set is capped; allows callers to detect silent truncation.
    total_matches: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        self.count = len(self.records)


class SearchMetadata(BaseModel):
    query: str
    field: str  # "ingredient" | "brand" | "company" | "din"
    timestamp: str
    normalized_terms: list[str] = Field(default_factory=list)
    per_source_status: dict[str, str] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    metadata: SearchMetadata
    sources: list[SourceResult]
    ai_summary: Optional[str] = None
