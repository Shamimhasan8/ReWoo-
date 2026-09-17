"""Constants used throughout the ReWoo framework."""

from pathlib import Path

# Default paths
DEFAULT_AUDIT_PATH = Path.home() / ".rewoo" / "audit.jsonl"
DEFAULT_CONFIG_DIR = Path.home() / ".rewoo"
DEFAULT_SKILLS_DIR = DEFAULT_CONFIG_DIR / "skills"

# Risk levels
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"

# Risk levels that require explicit approval
APPROVAL_REQUIRED_RISKS = {RISK_HIGH, RISK_CRITICAL}

# Default model
DEFAULT_MODEL = "claude-sonnet-4-6"

# Approval modes
APPROVAL_MODE_AUTO = "auto"
APPROVAL_MODE_CLI = "cli"
APPROVAL_MODE_NONE = "none"

# Execution status
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_SKIPPED = "skipped"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Sandbox
SANDBOX_ENABLED_DEFAULT = True

# Token tracking
MAX_PLAN_TOKENS = 4096
MAX_SOLVE_TOKENS = 4096
