"""LedgerFlow — invoice intake automation.

The package is organised around the pipeline in the spec:

    ingest -> extract -> validate -> gate -> sync

with cross-cutting concerns (observability, audit, retries) layered around it.
Every external dependency (LLM provider, storage, queue, downstream sync target)
sits behind a small interface so it can be swapped — that seam is the point.
"""

__version__ = "0.1.0"
