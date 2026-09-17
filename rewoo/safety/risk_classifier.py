"""Risk classifier for plan steps.

Analyzes each step in an execution plan and assigns a risk level based on
the tool being used, the arguments provided, and patterns of known
destructive operations.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from rewoo.core.types import PlanStep, RiskLevel

logger = logging.getLogger(__name__)

# Patterns that indicate destructive or high-risk operations
DESTRUCTIVE_PATTERNS = [
    # Shell command patterns
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\brm\s+-r\b"),
    re.compile(r"\brm\s+.*\*"),
    re.compile(r"\bdelete\b", re.IGNORECASE),
    re.compile(r"\bdrop\b", re.IGNORECASE),
    re.compile(r"\btruncate\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bchown\b"),
    re.compile(r">\s*/dev/sd"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bmkfs\b"),
    # File patterns
    re.compile(r"\boverwrite\b", re.IGNORECASE),
    re.compile(r"\berase\b", re.IGNORECASE),
    # Network patterns
    re.compile(r"\bcurl\s+.*\|\s*sh\b"),
    re.compile(r"\bwget\s+.*\|\s*sh\b"),
    re.compile(r"\bnc\s+-l\b"),
]

# Patterns that indicate moderate risk
MODERATE_PATTERNS = [
    re.compile(r"\bsudo\b"),
    re.compile(r"\bapt\s+install\b"),
    re.compile(r"\bpip\s+install\b"),
    re.compile(r"\bnpm\s+install\b"),
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgit\s+push\s+--force\b"),
    re.compile(r"\bmv\b"),
    re.compile(r"\bcp\s+-r\b"),
    re.compile(r"\bsed\s+-i\b"),
    re.compile(r"\bwrite\b", re.IGNORECASE),
    re.compile(r"\bmodify\b", re.IGNORECASE),
    re.compile(r"\bupdate\b", re.IGNORECASE),
    re.compile(r"\binstall\b", re.IGNORECASE),
]

# Tool-specific risk defaults
TOOL_RISK_DEFAULTS: dict[str, RiskLevel] = {
    "shell.run": RiskLevel.MEDIUM,
    "file.write": RiskLevel.MEDIUM,
    "file.delete": RiskLevel.HIGH,
    "file.read": RiskLevel.LOW,
    "web.search": RiskLevel.LOW,
    "web.scrape": RiskLevel.LOW,
    "web.request": RiskLevel.MEDIUM,
    "synthesize": RiskLevel.LOW,
}

# Tools that are always at least HIGH risk
ALWAYS_HIGH_TOOLS = {"file.delete"}

# Tools that are always CRITICAL risk
ALWAYS_CRITICAL_TOOLS: set[str] = set()


class RiskClassifier:
    """Classifies plan steps by risk level.

    The classifier uses a multi-signal approach:
    1. Tool-level defaults (e.g., file.delete is always HIGH)
    2. Argument pattern matching (e.g., rm -rf is HIGH/CRITICAL)
    3. Description keyword analysis
    4. Reversibility assessment
    """

    def classify(self, step: PlanStep) -> tuple[RiskLevel, str]:
        """Classify a single plan step by risk level.

        Args:
            step: The plan step to classify.

        Returns:
            A tuple of (risk_level, reason) explaining the classification.
        """
        # Check tool-level overrides first
        if step.tool in ALWAYS_CRITICAL_TOOLS:
            step.reversible = False
            return RiskLevel.CRITICAL, f"Tool '{step.tool}' is always classified as CRITICAL"

        if step.tool in ALWAYS_HIGH_TOOLS:
            step.reversible = False
            return RiskLevel.HIGH, f"Tool '{step.tool}' is always classified as HIGH"

        # Start with the tool default
        risk = TOOL_RISK_DEFAULTS.get(step.tool, RiskLevel.MEDIUM)
        reason = f"Default risk for tool '{step.tool}'"

        # Check arguments for destructive patterns
        args_str = str(step.tool_args)
        desc_str = step.description

        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern.search(args_str) or pattern.search(desc_str):
                if risk < RiskLevel.HIGH:
                    risk = RiskLevel.HIGH
                    reason = f"Destructive pattern detected: '{pattern.pattern}'"
                    break
                elif risk == RiskLevel.HIGH:
                    # Escalate to CRITICAL if already HIGH and more destructive signals
                    risk = RiskLevel.CRITICAL
                    reason = f"Multiple destructive indicators for step using '{step.tool}'"
                    break

        # Check for moderate risk patterns (only upgrade from LOW)
        if risk == RiskLevel.LOW:
            for pattern in MODERATE_PATTERNS:
                if pattern.search(args_str) or pattern.search(desc_str):
                    risk = RiskLevel.MEDIUM
                    reason = f"Moderate risk pattern detected: '{pattern.pattern}'"
                    break

        # Check for sudo — always at least HIGH
        if re.search(r"\bsudo\b", args_str) or re.search(r"\bsudo\b", desc_str):
            if risk < RiskLevel.HIGH:
                risk = RiskLevel.HIGH
                reason = "Step uses sudo (elevated privileges)"

        # Irreversible operations should not be marked as reversible
        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            step.reversible = False

        logger.debug(f"Step {step.index} classified as {risk.value}: {reason}")
        return risk, reason

    def classify_plan(self, steps: list[PlanStep]) -> list[PlanStep]:
        """Classify all steps in a plan.

        Args:
            steps: List of plan steps to classify.

        Returns:
            The same steps with risk_level and risk_reason updated.
        """
        for step in steps:
            risk, reason = self.classify(step)
            step.risk_level = risk
            step.risk_reason = reason
        return steps
