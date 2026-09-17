# Getting Started with ReWoo

## Installation

```bash
pip install rewoo
```

## Quick Start

1. Set your API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

2. Run a task:
   ```bash
   rewoo run "find all Python files modified today and summarize their changes"
   ```

3. Review the execution plan before it runs.

4. Approve or reject individual steps.

5. Get the synthesized result.

## Configuration

Create a `.env` file in your project directory:

```bash
REWOO_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
REWOO_APPROVAL_MODE=auto
REWOO_SANDBOX_ENABLED=true
```

## Using Different Models

```bash
# OpenAI GPT-4o
export OPENAI_API_KEY=sk-...
rewoo run "task" --model openai/gpt-4o

# OpenRouter
export OPENROUTER_API_KEY=sk-or-...
rewoo run "task" --model openrouter/anthropic/claude-3.5-sonnet
```

## Python SDK

```python
from rewoo import Agent
from rewoo.config import Settings

agent = Agent(settings=Settings(model="claude-sonnet-4-6"))

# Full run
result = await agent.run("Summarize the last 5 git commits")
print(result.answer)

# Plan only
plan = await agent.plan("Delete all .pyc files recursively")
for step in plan.steps:
    print(f"[{step.risk_level.value}] {step.tool}: {step.description}")
```

## Approval Modes

- **auto** (default): LOW/MEDIUM steps auto-approved, HIGH/CRITICAL require approval
- **cli**: All steps shown, interactive approval for each
- **none**: All steps approved automatically (dangerous)

## Audit Log

Every execution is logged to `~/.rewoo/audit.jsonl`:

```bash
rewoo audit --limit 10
```

## Next Steps

- Read the [Architecture Guide](./architecture.md) for a deep dive
- Read the [Safety Model](./safety-model.md) for risk classification details
- See [CONTRIBUTING.md](../CONTRIBUTING.md) to contribute
