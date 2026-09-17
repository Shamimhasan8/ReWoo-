"""Skills endpoints — manage learned skills from successful executions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter()


class SkillResponse(BaseModel):
    """Skill response."""
    id: str
    name: str
    description: str
    task_pattern: str
    use_count: int
    success_count: int
    last_used: str | None


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SkillResponse]:
    """List learned skills for the current user."""
    user_id = request.state.user_id

    from rewoo.db.models import Skill
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        skills = await Skill.list_by_user(session, user_id, limit=limit, offset=offset)
        return [
            SkillResponse(
                id=str(s.id),
                name=s.name,
                description=s.description,
                task_pattern=s.task_pattern,
                use_count=s.use_count,
                success_count=s.success_count,
                last_used=s.last_used.isoformat() if s.last_used else None,
            )
            for s in skills
        ]


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, request: Request) -> None:
    """Delete a learned skill."""
    user_id = request.state.user_id

    from rewoo.db.models import Skill
    from rewoo.db.session import get_db_session

    async with get_db_session() as session:
        deleted = await Skill.delete_by_id(session, skill_id, user_id=user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Skill not found")
