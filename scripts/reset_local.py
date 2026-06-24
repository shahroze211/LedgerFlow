"""Reset local state for a clean demo (SQLite path only).

Deletes the SQLite database and any uploaded bytes. For the docker stack use
`docker compose down -v` instead (clears the postgres volume).
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "backend" / "ledgerflow.db",
    ROOT / "ledgerflow.db",
]
DIRS = [
    ROOT / "backend" / "data",
    ROOT / "data",
]


def main() -> None:
    for db in TARGETS:
        if db.exists():
            db.unlink()
            print(f"removed {db}")
    for d in DIRS:
        if d.exists():
            shutil.rmtree(d)
            print(f"removed {d}/")
    print("local state reset. start the API and run scripts/seed_demo.py for a fresh batch.")


if __name__ == "__main__":
    main()
