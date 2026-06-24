"""Fuzzy vendor matching against the known-vendor master list (P2).

The LLM gives us a vendor *string*; finance needs a vendor *record* (with a
downstream account code). We never trust the raw string — we fuzzy-match it to a
curated list and flag anything that doesn't clear a threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import KnownVendor


@dataclass
class VendorMatch:
    matched: bool
    score: float  # 0–100
    name: str | None  # canonical vendor name
    account_code: str | None
    candidate: str | None  # what the model extracted


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def match_vendor(db: Session, raw_vendor: str | None) -> VendorMatch:
    settings = get_settings()
    if not raw_vendor or not raw_vendor.strip():
        return VendorMatch(False, 0.0, None, None, raw_vendor)

    vendors = db.query(KnownVendor).all()
    if not vendors:
        return VendorMatch(False, 0.0, None, None, raw_vendor)

    # Build a lookup of every alias/name -> canonical vendor.
    choices: dict[str, KnownVendor] = {}
    for v in vendors:
        choices[_normalize(v.name)] = v
        for alias in v.aliases or []:
            choices[_normalize(alias)] = v

    query = _normalize(raw_vendor)
    best = process.extractOne(query, list(choices.keys()), scorer=fuzz.token_sort_ratio)
    if best is None:
        return VendorMatch(False, 0.0, None, None, raw_vendor)

    label, score, _ = best
    vendor = choices[label]
    matched = score >= settings.vendor_match_threshold
    return VendorMatch(
        matched=matched,
        score=float(score),
        name=vendor.name if matched else None,
        account_code=vendor.account_code if matched else None,
        candidate=raw_vendor,
    )
