"""
CVKI M7.1 Deterministic Government Submission State Machine.
Enforces valid lifecycle transitions and prevents client-injected or invalid states.
"""

from app.schemas.government_integration import SubmissionLifecycleState


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""

    def __init__(self, current_state: SubmissionLifecycleState, target_state: SubmissionLifecycleState, reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        msg = f"Invalid submission state transition: '{current_state.value}' -> '{target_state.value}'."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)


# Explicit allowed transitions map
ALLOWED_TRANSITIONS: dict[SubmissionLifecycleState, set[SubmissionLifecycleState]] = {
    SubmissionLifecycleState.READY: {
        SubmissionLifecycleState.QUEUED,
        SubmissionLifecycleState.SUBMITTING,
        SubmissionLifecycleState.VALIDATION_FAILED,
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.VALIDATION_FAILED: {
        SubmissionLifecycleState.READY,
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.QUEUED: {
        SubmissionLifecycleState.SUBMITTING,
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.SUBMITTING: {
        SubmissionLifecycleState.SUBMITTED,
        SubmissionLifecycleState.UNKNOWN_OUTCOME,
        SubmissionLifecycleState.REJECTED,
        SubmissionLifecycleState.FAILED,
    },
    SubmissionLifecycleState.UNKNOWN_OUTCOME: {
        SubmissionLifecycleState.SUBMITTED,  # Reconciled: external government confirmed receipt
        SubmissionLifecycleState.READY,      # Reconciled: external government confirmed nonexistent, reset for clean retry
        SubmissionLifecycleState.FAILED,     # Reconciliation failure or unrecoverable external state
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.SUBMITTED: {
        SubmissionLifecycleState.STATUS_SYNCING,
        SubmissionLifecycleState.COMPLETED,
        SubmissionLifecycleState.REJECTED,
    },
    SubmissionLifecycleState.STATUS_SYNCING: {
        SubmissionLifecycleState.SUBMITTED,
        SubmissionLifecycleState.COMPLETED,
        SubmissionLifecycleState.FAILED,
    },
    SubmissionLifecycleState.FAILED: {
        SubmissionLifecycleState.READY,      # Retry eligibility
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.REJECTED: {
        SubmissionLifecycleState.READY,      # Correction and re-attempt
        SubmissionLifecycleState.CANCELLED,
    },
    SubmissionLifecycleState.CANCELLED: set(),  # Terminal
    SubmissionLifecycleState.COMPLETED: set(),  # Terminal
}


class SubmissionStateMachine:
    @staticmethod
    def can_transition(
        current_state: SubmissionLifecycleState,
        target_state: SubmissionLifecycleState,
    ) -> bool:
        """Returns True if transition from current_state to target_state is strictly permitted."""
        if current_state == target_state:
            return True
        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        return target_state in allowed

    @classmethod
    def validate_transition(
        cls,
        current_state: SubmissionLifecycleState,
        target_state: SubmissionLifecycleState,
        context: str = "",
    ) -> SubmissionLifecycleState:
        """
        Validates transition. Returns target_state if valid, or raises InvalidStateTransitionError.
        """
        if not cls.can_transition(current_state, target_state):
            raise InvalidStateTransitionError(
                current_state=current_state,
                target_state=target_state,
                reason=context or "State transition disallowed by M7.1 lifecycle policy.",
            )
        return target_state
