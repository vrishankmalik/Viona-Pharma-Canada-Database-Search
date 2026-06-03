"""
Optional cross-source de-duplication and plain-language summary using llama3.
All functions degrade gracefully if Ollama is not running.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.models import DrugRecord, SourceResult


async def _call_ollama(prompt: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json().get("response", "").strip()
    except Exception:
        return None


async def generate_summary(
    query: str,
    sources: list[SourceResult],
) -> Optional[str]:
    """Generate a plain-language summary of results across sources."""
    counts = {s.source: s.count for s in sources}
    errors = {s.source: s.error_message for s in sources if s.status == "error"}

    # Build a concise data summary for the LLM
    records_snippet = []
    for s in sources:
        if s.records:
            sample = s.records[:3]
            for r in sample:
                records_snippet.append(
                    f"[{r.source}] {r.brand_name or 'N/A'} | {r.ingredient or 'N/A'} | "
                    f"{r.company or 'N/A'} | Status: {r.status or 'N/A'}"
                )

    prompt = (
        f"A user searched Canadian drug databases for '{query}'. "
        f"Here are the result counts per database: {json.dumps(counts)}. "
        f"Sample records:\n" + "\n".join(records_snippet[:12]) + "\n\n"
        f"Write a 2-4 sentence plain-language summary of what was found. "
        f"Be factual and concise. Do not invent information. "
        f"Mention if any sources had errors: {json.dumps(errors) if errors else 'none'}. "
        f"Start with 'AI Summary:'"
    )

    return await _call_ollama(prompt)
