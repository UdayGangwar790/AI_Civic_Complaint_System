"""
CVKI Research v2.x - R0 Status Machine
Defines valid lifecycle states and strict transitions for research experiments.
"""

from enum import Enum


class ResearchStatus(str, Enum):
    """Lifecycle status for CVKI Research v2.x experiments."""
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    ARCHIVED = "ARCHIVED"


# Valid state transitions
VALID_TRANSITIONS: dict[ResearchStatus, set[ResearchStatus]] = {
    ResearchStatus.PLANNED: {ResearchStatus.RUNNING, ResearchStatus.BLOCKED, ResearchStatus.ARCHIVED},
    ResearchStatus.RUNNING: {ResearchStatus.COMPLETED, ResearchStatus.FAILED, ResearchStatus.BLOCKED},
    ResearchStatus.COMPLETED: {ResearchStatus.ARCHIVED},
    ResearchStatus.FAILED: {ResearchStatus.ARCHIVED},
    ResearchStatus.BLOCKED: {ResearchStatus.PLANNED, ResearchStatus.ARCHIVED},
    ResearchStatus.ARCHIVED: set(),  # Terminal state
}


class InvalidStatusTransitionError(ValueError):
    """Raised when an illegal lifecycle state transition is attempted."""
    pass


def validate_status_transition(
    current_status: ResearchStatus | str,
    new_status: ResearchStatus | str,
) -> None:
    """
    Validates that a transition from current_status to new_status conforms to the research state machine.
    Raises InvalidStatusTransitionError if the transition is prohibited.
    """
    current = ResearchStatus(current_status)
    target = ResearchStatus(new_status)

    if current == target:
        return

    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStatusTransitionError(
            f"Illegal status transition: cannot transition experiment from '{current.value}' to '{target.value}'. "
            f"Allowed transitions from '{current.value}': {[s.value for s in allowed]}"
        )
