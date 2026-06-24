"""Folder-watch ingestion (M1).

Drop a file into the watched directory and it is ingested, deduped and enqueued —
the "drop folder in -> records sync out" half of the demo. Backed by watchdog,
with a one-shot ``scan_existing`` for files already present at startup.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..config import get_settings
from ..db import session_scope
from ..queue import get_queue
from .service import ingest_path

_INGESTIBLE = {".txt", ".md", ".csv", ".pdf", ".text", ""}


def _handle(path: Path) -> None:
    if not path.is_file() or path.suffix.lower() not in _INGESTIBLE:
        return
    with session_scope() as db:
        outcome = ingest_path(db, str(path))
        invoice_id = outcome.invoice.id
        duplicate = outcome.duplicate
    if not duplicate:
        get_queue().enqueue(invoice_id)
        print(f"[watch] ingested {path.name} -> {invoice_id}")
    else:
        print(f"[watch] duplicate ignored: {path.name}")


def scan_existing(watch_dir: str | None = None) -> int:
    settings = get_settings()
    directory = Path(watch_dir or settings.watch_dir)
    directory.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(directory.iterdir()):
        _handle(path)
        count += 1
    return count


def watch_folder(watch_dir: str | None = None) -> None:
    """Block, ingesting any file that appears in the watch directory."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    settings = get_settings()
    directory = Path(watch_dir or settings.watch_dir)
    directory.mkdir(parents=True, exist_ok=True)

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                # small delay so the writer finishes flushing the file
                time.sleep(0.2)
                _handle(Path(event.src_path))

    scan_existing(str(directory))
    observer = Observer()
    observer.schedule(_Handler(), str(directory), recursive=False)
    observer.start()
    print(f"[watch] watching {directory.resolve()} for invoices...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
