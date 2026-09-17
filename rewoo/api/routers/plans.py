"""Plan management endpoints — create, view, and manage execution plans.

Plans are the core resource in ReWoo. This endpoint handles plan creation
(uses LLM), retrieval, and approval workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter()


class PlanCreateRequest(BaseModel):
    """Request to create a new execution plan."""
    task: str = Field(min_length=1, max_length=10000, description="The task to plan for")
    model: Optional[str] = Field(default=None, description="Override the model to use")
    approval_mode: Optional[str] = Field(default=None, pattern="^(auto|cli|none)$")
    sandbox_enabled: Optional[bool] = Field(default=None)


class PlanStepResponse(BaseModel):
    """A single step in a plan response."""
    index: int
    description: str
    tool: str
    tool_args: dict
    risk_level: str
    risk_reason: Optional[str] = None
    depends_on: list[int]
    status: str
    reversible: bool


class PlanResponse(BaseModel):
    """Execution plan response."""
    id: str
    task: str
    steps: list[PlanStepResponse]
    has_high_risk: bool
    created_at: str
    status: str


class PlanApprovalRequest(BaseModel):
    """Request to approve/reject plan steps."""
    approvals: dict[int, str] = Field(description="Map of step index to 'approve', 'reject', or 'skip'")


@router.post("", response_model=PlanResponse, status_code=201)
async def create_plan(req: PlanCreateRequest, request: Request) -> PlanResponse:
    """Create a new execution plan.

    Uses the LLM to generate a complete execution plan for the given task.
    The plan is NOT executed — it must be explicitly approved first.
    """
    user_id = request.state.user_id

    from rewoo.agent.loop import Agent
    from rewoo.config import Settings

    settings = Settings()
    if req.model:
        settings.model = req.model
    if req.approval_mode:
        settings.approval_mode = req.approval_mode
    if req.sandbox_enabled is not None:
        settings.sandbox_enabled = req.sandbox_enabled

    agent = Agent(settings=settings)

    plan = await agent.plan(req.task)

    # Store plan in database
    from rewoo.db.models import ExecutionPlan as PlanModel
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        plan_model = await PlanModel.create_from_plan(
            session,
            plan=plan,
            user_id=user_id,
        )

        return PlanResponse(
            id=str(plan_model.id),
            task=plan.task,
            steps=[
                PlanStepResponse(
                    index=s.index,
                    description=s.description,
                    tool=s.tool,
                    tool_args=s.tool_args,
                    risk_level=s.risk_level.value,
                    risk_reason=s.risk_reason,
                    depends_on=s.depends_on,
                    status=s.status.value,
                    reversible=s.reversible,
                )
                for s in plan.steps
            ],
            has_high_risk=plan.has_high_risk,
            created_at=plan.created_at.isoformat(),
            status="pending_approval",
        )


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str, request: Request) -> PlanResponse:
    """Get an execution plan by ID."""
    user_id = request.state.user_id

    from rewoo.db.models import ExecutionPlan as PlanModel
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        plan = await PlanModel.get_by_id(session, plan_id, user_id=user_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        return PlanResponse(
            id=str(plan.id),
            task=plan.task,
            steps=[
                PlanStepResponse(
                    index=s["index"],
                    description=s["description"],
                    tool=s["tool"],
                    tool_args=s["tool_args"],
                    risk_level=s["risk_level"],
                    risk_reason=s.get("risk_reason"),
                    depends_on=s.get("depends_on", []),
                    status=s.get("status", "pending"),
                    reversible=s.get("reversible", True),
                )
                for s in plan.steps_data
            ],
            has_high_risk=plan.has_high_risk,
            created_at=plan.created_at.isoformat(),
            status=plan.status,
        )


@router.post("/{plan_id}/approve", response_model=PlanResponse)
async def approve_plan(plan_id: str, req: PlanApprovalRequest, request: Request) -> PlanResponse:
    """Approve or reject individual steps in a plan."""
    user_id = request.state.user_id

    from rewoo.db.models import ExecutionPlan as PlanModel
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        plan = await PlanModel.get_by_id(session, plan_id, user_id=user_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if plan.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Plan is not in pending_approval state")

        # Update step statuses based on approvals
        await plan.apply_approvals(session, req.approvals)

        return await get_plan(plan_id, request)


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PlanResponse]:
    """List execution plans for the current user."""
    user_id = request.state.user_id

    from rewoo.db.models import ExecutionPlan as PlanModel
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        plans = await PlanModel.list_by_user(session, user_id, limit=limit, offset=offset)
        result = []
        for p in plans:
            result.append(PlanResponse(
                id=str(p.id),
                task=p.task,
                steps=[
                    PlanStepResponse(
                        index=s["index"],
                        description=s["description"],
                        tool=s["tool"],
                        tool_args=s["tool_args"],
                        risk_level=s["risk_level"],
                        risk_reason=s.get("risk_reason"),
                        depends_on=s.get("depends_on", []),
                        status=s.get("status", "pending"),
                        reversible=s.get("reversible", True),
                    )
                    for s in p.steps_data
                ],
                has_high_risk=p.has_high_risk,
                created_at=p.created_at.isoformat(),
                status=p.status,
            ))
        return result
