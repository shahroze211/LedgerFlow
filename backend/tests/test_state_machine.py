"""M0 acceptance: invalid status transitions must raise, not pass (P8)."""

import pytest

from app.models import InvalidTransition, Status, assert_transition, can_transition


def test_legal_transition_passes():
    assert_transition(Status.queued, Status.extracting)
    assert can_transition(Status.auto_approved, Status.synced)


def test_illegal_transition_raises():
    # you can never jump straight from queued to synced — it must pass the gate.
    with pytest.raises(InvalidTransition):
        assert_transition(Status.queued, Status.synced)


def test_synced_is_terminal():
    with pytest.raises(InvalidTransition):
        assert_transition(Status.synced, Status.needs_review)


def test_dead_letter_cannot_silently_become_approved():
    with pytest.raises(InvalidTransition):
        assert_transition(Status.dead_letter, Status.auto_approved)
