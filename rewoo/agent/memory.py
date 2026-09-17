"""Persistent memory and skill learning for ReWoo agents.

Learns patterns from successful executions and stores them as reusable
skills (inspired by Hermes' learning loop). Skills capture the mapping
from task patterns to execution plans, allowing the Planner to reuse
successful strategies.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Skill(BaseModel):
    """A learned skill — a reusable execution pattern.

    Skills are created from successful executions and store the
    mapping from a task pattern to an execution plan template.
    """

    id: str = Field(default_factory=lambda: f"skill_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    name: str = Field(description="Short name for the skill")
    description: str = Field(description="What this skill does")
    task_pattern: str = Field(description="Regex pattern matching tasks this skill applies to")
    plan_template: list[dict[str, Any]] = Field(description="Template for plan steps")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    use_count: int = 0
    success_count: int = 0
    last_used: datetime | None = None


class Memory:
    """Manages persistent memory and learned skills.

    Skills are stored as JSON files in the skills directory.
    Each skill captures a successful execution pattern that can
    be reused for similar future tasks.
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        """Initialize the memory system.

        Args:
            skills_dir: Directory for storing learned skills.
                        Defaults to ~/.rewoo/skills/
        """
        self.skills_dir = skills_dir or Path.home() / ".rewoo" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        """Load all skills from the skills directory."""
        if not self.skills_dir.exists():
            return

        for path in self.skills_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skill = Skill(**data)
                self._skills[skill.id] = skill
            except Exception as e:
                logger.warning(f"Failed to load skill from {path}: {e}")

        logger.info(f"Loaded {len(self._skills)} skills")

    def _save_skill(self, skill: Skill) -> None:
        """Save a skill to disk.

        Args:
            skill: The skill to save.
        """
        path = self.skills_dir / f"{skill.id}.json"
        try:
            path.write_text(skill.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save skill {skill.id}: {e}")

    def learn_from_execution(
        self,
        task: str,
        plan_steps: list[dict[str, Any]],
        success: bool,
    ) -> Skill | None:
        """Learn a skill from a completed execution.

        Only learns from successful executions. Creates a skill with
        a task pattern and plan template that can be reused.

        Args:
            task: The original task description.
            plan_steps: The execution plan steps as dicts.
            success: Whether the execution succeeded.

        Returns:
            The learned Skill, or None if the execution failed.
        """
        if not success:
            return None

        # Generate a simple task pattern from the task description
        # Extract key words (nouns/verbs) for pattern matching
        import re
        words = re.findall(r"\b\w{4,}\b", task.lower())
        pattern = ".*".join(words[:3]) if words else re.escape(task[:30])

        skill = Skill(
            name=f"skill_{len(self._skills) + 1}",
            description=f"Learned from: {task[:100]}",
            task_pattern=pattern,
            plan_template=plan_steps,
            use_count=0,
            success_count=0,
        )

        self._skills[skill.id] = skill
        self._save_skill(skill)
        logger.info(f"Learned new skill: {skill.id}")
        return skill

    def find_matching_skill(self, task: str) -> Skill | None:
        """Find a previously learned skill that matches the task.

        Args:
            task: The task to match against.

        Returns:
            The best matching Skill, or None if no match found.
        """
        import re

        best_skill: Skill | None = None
        best_score = 0

        for skill in self._skills.values():
            try:
                if re.search(skill.task_pattern, task, re.IGNORECASE):
                    # Simple scoring: prefer more specific patterns and more successful skills
                    score = skill.success_count + 1
                    if score > best_score:
                        best_score = score
                        best_skill = skill
            except re.error:
                continue

        return best_skill

    def record_skill_usage(self, skill_id: str, success: bool) -> None:
        """Record that a skill was used.

        Args:
            skill_id: The ID of the skill that was used.
            success: Whether the usage was successful.
        """
        skill = self._skills.get(skill_id)
        if not skill:
            return

        skill.use_count += 1
        if success:
            skill.success_count += 1
        skill.last_used = datetime.now(timezone.utc)
        self._save_skill(skill)

    def list_skills(self) -> list[Skill]:
        """List all learned skills.

        Returns:
            List of all skills, sorted by use count (most used first).
        """
        return sorted(self._skills.values(), key=lambda s: s.use_count, reverse=True)

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a learned skill.

        Args:
            skill_id: The ID of the skill to delete.

        Returns:
            True if the skill was deleted, False if not found.
        """
        skill = self._skills.pop(skill_id, None)
        if not skill:
            return False

        path = self.skills_dir / f"{skill_id}.json"
        if path.exists():
            path.unlink()

        logger.info(f"Deleted skill: {skill_id}")
        return True
