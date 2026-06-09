"""DIN (Drug Identification Number) normalization utilities.

A Canadian DIN is always 8 decimal digits, zero-padded on the left.
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_din(din: str) -> Optional[str]:
    """Strip non-digits, zero-pad to 8.  Returns None for empty / non-numeric input."""
    digits = re.sub(r"\D", "", din.strip())
    if not digits:
        return None
    return digits.zfill(8)


def parse_dins(raw: Optional[str]) -> list[str]:
    """Split a raw multi-DIN string into a list of normalized DINs.

    Health Canada NOC pages sometimes emit strings like:
        "02535742,; 02535750,; 02535734"
    This function handles all common separators and returns clean 8-digit DINs.
    """
    if not raw or not raw.strip():
        return []
    parts = re.split(r"[;,\s]+", raw.strip())
    result: list[str] = []
    for part in parts:
        normalized = normalize_din(part)
        if normalized:
            result.append(normalized)
    return result


def is_valid_din(din: str) -> bool:
    """Return True iff the string is exactly 8 decimal digits."""
    return bool(re.fullmatch(r"\d{8}", din))
