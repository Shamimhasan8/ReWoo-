"""Execution endpoints — run approved plans and track execution progress.

Executions are long-running tasks that go through the full
Planner→Reviewer→Worker→Solver cycle. Results are streamed via
WebSocket and stored in the database.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import logging

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class ExecutionCreateRequest(BaseModel):
    """Request to execute a plan."""
    plan_id: str
    approval_mode: Optional[str] = Field(default=None, pattern="^(auto|cli|none)$")


class ExecutionResponse(BaseModel):
    """Execution response."""
    id: str
    plan_id: str
    task: str
    status: str
    answer: Optional[str] = None
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    step_results: list[dict] = []
    created_at: str
    completed_at: Optional[str] = None


class ExecutionListResponse(BaseModel):
    """Paginated execution list."""
    items: list[ExecutionResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=ExecutionResponse, status_code=202)
async def create_execution(req: ExecutionCreateRequest, request: Request) -> ExecutionResponse:
    """Start executing an approved plan.

    Returns immediately with status='running'. The actual execution
    happens asynchronously via the task queue.
    """
    user_id = request.state.user_id

    from rewoo.db.models import Execution, ExecutionPlan as PlanModel
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        plan = await PlanModel.get_by_id(session, req.plan_id, user_id=user_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        if plan.status not in ("pending_approval", "approved"):
            raise HTTPException(status_code=400, detail=f"Plan status '{plan.status}' cannot be executed")

        # Create execution record
        execution = await Execution.create(
            session,
            plan_id=plan.id,
            user_id=user_id,
            task=plan.task,
            status="queued",
        )

    # Enqueue the execution task
    from rewoo.tasks.executor import execute_plan_task
    execute_plan_task.delay(str(execution.id), str(plan.id), user_id, req.approval_mode)

    return ExecutionResponse(
        id=str(execution.id),
        plan_id=str(plan.id),
        task=plan.task,
        status="queued",
        created_at=execution.created_at.isoformat(),
    )


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str, request: Request) -> ExecutionResponse:
    """Get the status and results of an execution."""
    user_id = request.state.user_id

    from rewoo.db.models import Execution
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        execution = await Execution.get_by_id(session, execution_id, user_id=user_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")

        return ExecutionResponse(
            id=str(execution.id),
            plan_id=str(execution.plan_id),
            task=execution.task,
            status=execution.status,
            answer=execution.answer,
            total_tokens=execution.total_tokens,
            total_duration_seconds=execution.total_duration_seconds,
            step_results=execution.step_results_data,
            created_at=execution.created_at.isoformat(),
            completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
        )


@router.get("", response_model=ExecutionListResponse)
async def list_executions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ExecutionListResponse:
    """List executions for the current user."""
    user_id = request.state.user_id

    from rewoo.db.models import Execution
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        executions, total = await Execution.list_by_user(session, user_id, limit=limit, offset=offset)
        items = [
            ExecutionResponse(
                id=str(e.id),
                plan_id=str(e.plan_id),
                task=e.task,
                status=e.status,
                answer=e.answer,
                total_tokens=e.total_tokens,
                total_duration_seconds=e.total_duration_seconds,
                step_results=e.step_results_data,
                created_at=e.created_at.isoformat(),
                completed_at=e.completed_at.isoformat() if e.completed_at else None,
            )
            for e in executions
        ]
        return ExecutionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.websocket("/ws/{execution_id}")
async def execution_websocket(websocket: WebSocket, execution_id: str) -> None:
    """WebSocket endpoint for real-time execution progress.

    Streams step-by-step progress updates as the execution proceeds.
    """
    await websocket.accept()

    try:
        from rewoo.cache.redis import get_redis
        redis = await get_redis()

        if redis:
            # Subscribe to execution updates via Redis pub/sub
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"execution:{execution_id}")

            try:
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=30.0,
                    )
                    if message and message["type"] == "message":
                        await websocket.send_text(message["data"].decode())

                    # Also check if client wants to cancel
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                        if data == "cancel":
                            await redis.publish(
                                f"execution:cancel:{execution_id}",
                                "cancel",
                            )
                            break
                    except asyncio.TimeoutError:
                        pass
            finally:
                await pubsub.unsubscribe(f"execution:{execution_id}")
        else:
            # Fallback: poll the database
            from rewoo.db.models import Execution
            from rewoo.db.session import get_db_session

            last_status = None
            while True:
                async with get_db_session() as session:
                    execution = await Execution.get_by_id(session, execution_id)
                    if execution and execution.status != last_status:
                        last_status = execution.status
                        await websocket.send_json({
                            "status": execution.status,
                            "answer": execution.answer,
                        })

                    if execution and execution.status in ("completed", "failed", "cancelled"):
                        break

                await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for execution {execution_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass

