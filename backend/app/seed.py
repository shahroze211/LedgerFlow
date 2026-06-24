"""Seed the known-vendor master list (idempotent).

This is the curated list the validator fuzzy-matches extracted vendor strings
against. In a real deployment this comes from the customer's vendor master in
their ERP; here it's a fixed set chosen to line up with the eval fixtures.
"""

from __future__ import annotations

from .db import session_scope
from .models import KnownVendor

KNOWN_VENDORS: list[dict] = [
    {"name": "Acme Corporation", "aliases": ["Acme Corp", "ACME"], "account_code": "5000-OFFICE"},
    {"name": "Globex Corporation", "aliases": ["Globex", "Globex Corp"], "account_code": "5100-SAAS"},
    {"name": "Initech LLC", "aliases": ["Initech", "Initech Inc"], "account_code": "5200-CONSULT"},
    {"name": "Umbrella Industries", "aliases": ["Umbrella", "Umbrella Inc"], "account_code": "5300-LAB"},
    {"name": "Stark Industries", "aliases": ["Stark", "Stark Ind"], "account_code": "5400-HARDWARE"},
    {"name": "Wayne Enterprises", "aliases": ["Wayne Ent", "Wayne Corp"], "account_code": "5500-FACILITIES"},
    {"name": "Soylent Foods Ltd", "aliases": ["Soylent", "Soylent Foods"], "account_code": "5600-CATERING"},
    {"name": "Hooli Inc", "aliases": ["Hooli"], "account_code": "5700-CLOUD"},
    {"name": "Vandelay Imports", "aliases": ["Vandelay", "Vandelay Industries"], "account_code": "5800-LOGISTICS"},
    {"name": "Cyberdyne Systems", "aliases": ["Cyberdyne"], "account_code": "5900-RND"},
]


def seed_known_vendors() -> int:
    """Insert any missing known vendors. Returns the number inserted."""
    inserted = 0
    with session_scope() as db:
        existing = {v.name for v in db.query(KnownVendor).all()}
        for spec in KNOWN_VENDORS:
            if spec["name"] in existing:
                continue
            db.add(
                KnownVendor(
                    name=spec["name"],
                    aliases=spec["aliases"],
                    account_code=spec["account_code"],
                )
            )
            inserted += 1
    return inserted


if __name__ == "__main__":
    print(f"seeded {seed_known_vendors()} known vendors")
