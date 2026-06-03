"""XLSX export — one sheet per source plus combined, by-combination, and metadata tabs."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

from app.grouping import combination_label, group_records, make_combination_key
from app.models import SearchResponse, SourceResult

_SOURCE_DISPLAY = {
    "DPD": "Drug Product Database (DPD)",
    "GenericSubmissions": "Generic Submissions Under Review",
    "NOC": "Notice of Compliance (NOC)",
    "PatentRegister": "Patent Register",
}


def _records_to_df(source_result: SourceResult) -> pd.DataFrame:
    if not source_result.records:
        return pd.DataFrame(
            columns=["combination", "source", "ingredient", "brand_name", "company", "din",
                     "strength", "dosage_form", "route", "status", "record_url"]
        )
    rows = []
    for r in source_result.records:
        key = make_combination_key(r)
        row: dict[str, Any] = {
            "combination": combination_label(key),
            "source": r.source,
            "ingredient": r.ingredient,
            "brand_name": r.brand_name,
            "company": r.company,
            "din": r.din,
            "strength": r.strength,
            "dosage_form": r.dosage_form,
            "route": r.route,
            "status": r.status,
            "record_url": r.record_url,
        }
        # Flatten source_specific into separate columns
        for k, v in r.source_specific.items():
            row[f"_{k}"] = v
        rows.append(row)
    df = pd.DataFrame(rows)
    df = df.sort_values("combination", kind="stable").reset_index(drop=True)
    return df


def _build_combination_summary(response: SearchResponse) -> pd.DataFrame:
    all_records = [r for sr in response.sources for r in sr.records]
    groups = group_records(all_records)
    rows = [
        {
            "Combination": g.label,
            "Product Count": g.product_count,
            "Company Count": g.company_count,
            "Companies": ", ".join(g.companies),
        }
        for g in groups
    ]
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["Combination", "Product Count", "Company Count", "Companies"])


def _autofit_widths(worksheet: Any, df: pd.DataFrame) -> None:
    for i, col in enumerate(df.columns, 1):
        col_str_len = df[col].fillna("").astype(str).str.len().max() if not df.empty else 0
        max_len = max(len(str(col)), int(col_str_len) if not __import__("math").isnan(float(col_str_len or 0)) else 0)
        col_letter = worksheet.cell(row=1, column=i).column_letter
        worksheet.column_dimensions[col_letter].width = min(max_len + 2, 60)


def build_xlsx(response: SearchResponse) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Per-source sheets
        all_dfs: list[pd.DataFrame] = []
        for source_result in response.sources:
            df = _records_to_df(source_result)
            sheet_name = _SOURCE_DISPLAY.get(source_result.source, source_result.source)[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            _autofit_widths(ws, df)
            if not df.empty:
                all_dfs.append(df)

        # Combined sheet
        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            combined = combined.sort_values("combination", kind="stable").reset_index(drop=True)
        else:
            combined = pd.DataFrame()
        combined.to_excel(writer, sheet_name="Combined", index=False)
        ws_c = writer.sheets["Combined"]
        ws_c.freeze_panes = "A2"
        if not combined.empty:
            _autofit_widths(ws_c, combined)

        # By Combination summary sheet
        combo_df = _build_combination_summary(response)
        combo_df.to_excel(writer, sheet_name="By Combination", index=False)
        ws_combo = writer.sheets["By Combination"]
        ws_combo.freeze_panes = "A2"
        _autofit_widths(ws_combo, combo_df)

        # Metadata sheet
        meta_rows = [
            {"field": "Query", "value": response.metadata.query},
            {"field": "Search field", "value": response.metadata.field},
            {"field": "Timestamp", "value": response.metadata.timestamp},
            {"field": "Normalized terms", "value": ", ".join(response.metadata.normalized_terms)},
        ]
        for source, status in response.metadata.per_source_status.items():
            meta_rows.append({"field": f"{source} status", "value": status})
        if response.ai_summary:
            meta_rows.append({"field": "AI Summary", "value": response.ai_summary})

        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="Search Metadata", index=False)
        ws_m = writer.sheets["Search Metadata"]
        ws_m.freeze_panes = "A2"
        ws_m.column_dimensions["A"].width = 24
        ws_m.column_dimensions["B"].width = 80

    return buf.getvalue()
