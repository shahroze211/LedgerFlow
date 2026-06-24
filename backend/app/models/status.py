"""Invoice status — a strict state machine.

Spec §6: "Status is a strict state machine — invalid transitions must raise, not
pass." That guard is what makes the audit trail trustworthy: a record can never
reach ``synced`` without having passed through the gate, and a ``dead_letter`` can
never silently resurrect as ``auto_approved``.
"""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    queued = "queued"  # ingested, waiting for a worker
    extracting = "extracting"  # worker is running the extract->validate->gate pipeline
    needs_review = "needs_review"  # gate routed it to a human (P1)
    auto_approved = "auto_approved"  # passed the gate with no human touch
    approved = "approved"  # a human approved it from the review console
    synced = "synced"  # written downstream exactly once (P5)
    dead_letter = "dead_letter"  # exhausted retries; surfaced, never dropped (P4)


# Adjacency list of *allowed* transitions. Anything not listed raises.
_ALLOWED: dict[Status, frozenset[Status]] = {
    Status.queued: frozenset({Status.extracting, Status.dead_letter}),
    Status.extracting: frozenset(
        {
            Status.auto_approved,
            Status.needs_review,
            Status.queued,  # transient failure -> requeue for retry (P4)
            Status.dead_letter,  # retries exhausted
        }
    ),
    # A human edit re-runs validation; it may still fail and stay in review.
    Status.needs_review: frozenset(
        {Status.approved, Status.auto_approved, Status.needs_review, Status.dead_letter}
    ),
    Status.auto_approved: frozenset({Status.synced, Status.dead_letter}),
    Status.approved: frozenset({Status.synced, Status.dead_letter}),
    Status.synced: frozenset(),  # terminal (re-sync is idempotent, no status change)
    Status.dead_letter: frozenset({Status.queued}),  # operator may requeue
}

# Statuses from which a record is eligible to be written downstream (P5).
SYNCABLE: frozenset[Status] = frozenset({Status.auto_approved, Status.approved})


class InvalidTransition(Exception):
    """Raised when code attempts a status transition the machine forbids."""


def can_transition(current: Status, target: Status) -> bool:
    return target in _ALLOWED.get(current, frozenset())


def assert_transition(current: Status, target: Status) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(
            f"illegal invoice status transition: {current.value} -> {target.value}"
        )
