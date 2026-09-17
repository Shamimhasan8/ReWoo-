"""Reviewer module — displays plans and collects approvals.

The Reviewer sits between the Planner and the Worker in the ReWOO
architecture. It presents the execution plan to the user (or an
automated system) and collects approval decisions before any
execution begins.

This module is a thin wrapper around the approval gate implementations
in rewoo.safety.approval_gate, providing a unified interface for the
agent loop.
"""

from __future__ import annotations

import logging

from rewoo.config import Settings
from rewoo.core.types import ExecutionPlan
from rewoo.safety.approval_gate import ApprovalGate, create_approval_gate
from rewoo.safety.audit import AuditLogger

logger = logging.getLogger(__name__)


class Reviewer:
    """Reviews execution plans and collects approval decisions.

    The Reviewer uses the configured approval gate (CLI, auto, or none)
    to present the plan and collect decisions. All decisions are logged
    to the audit log for traceability.
    """

    def __init__(
        self,
        settings: Settings,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.settings = settings
        self.gate: ApprovalGate = create_approval_gate(settings)
        self.audit = audit_logger or AuditLogger(path=settings.audit_path)

    def review(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Review an execution plan and collect approval decisions.

        Displays the plan using the configured approval gate and
        returns the plan with approval statuses set on each step.

        Args:
            plan: The execution plan to review.

        Returns:
            The plan with approval statuses updated.
        """
        logger.info(f"Reviewing plan {plan.id} with {plan.step_count} steps")

        # Log the plan creation
        self.audit.log_plan_created(plan)

        # Run the approval gate
        reviewed_plan = self.gate.review_plan(plan)

        # Log approval/rejection decisions
        for step in reviewed_plan.steps:
            if step.status.value == "approved":
                self.audit.log_step_approved(plan.id, step)
            elif step.status.value == "rejected":
                self.audit.log_step_rejected(plan.id, step, reason="User rejected")

        approved = sum(1 for s in reviewed_plan.steps if s.status.value == "approved")
        rejected = sum(1 for s in reviewed_plan.steps if s.status.value == "rejected")
        skipped = sum(1 for s in reviewed_plan.steps if s.status.value == "skipped")

        logger.info(
            f"Review complete: {approved} approved, {rejected} rejected, {skipped} skipped"
        )

        return reviewed_plan
