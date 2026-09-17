<div align="center">

# 🪢 ReWoo

**Reason first. Execute safely. Learn always.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://img.shields.io/github/actions/workflow/status/rewooai/rewoo/ci.yml?branch=main&label=CI)](https://github.com/rewooai/rewoo/actions)
[![codecov](https://codecov.io/gh/rewooai/rewoo/branch/main/graph/badge.svg)](https://codecov.io/gh/rewooai/rewoo)

A **low-risk, plan-first AI agent framework** built on the ReWOO architecture —
the only open-source agent that shows you the full execution plan *before* doing anything.

Production-ready: FastAPI + PostgreSQL + Redis + Celery + K8s + Observability.

[Quickstart](#quickstart) · [Architecture](#architecture) · [API](#rest-api) · [Deploy](#production-deployment) · [Docs](./docs/getting-started.md)

</div>

---

## The Problem with Every Other Agent

OpenClaw, Hermes, LangChain, AutoGen — they all execute reactively. The agent reasons one step, calls a tool, observes, reasons again. You never see what it's planning to do. Destructive shell commands run silently. Token costs compound with every observation. By the time you notice something went wrong, it already did.

**ReWoo fixes this at the architectural level.**

## How ReWoo Works

ReWoo is an implementation of the [ReWOO paper](https://arxiv.org/abs/2305.18323) (Reasoning Without Observations) — a Planner/Worker/Solver architecture that decouples *planning* from *execution*.

```
Your task
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  PLANNER                                             │
│  Generates a complete execution plan with            │
│  ALL tool calls identified — no execution yet.       │
│  Output: structured steps with risk levels.          │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  REVIEWER  (the ReWoo innovation)                    │
│  Shows you the full plan. Risk-classified.           │
│  HIGH/CRITICAL steps require your approval.          │
│  You can modify or reject any step.                  │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  WORKER                                              │
│  Executes each approved step in dependency order.    │
│  Sandboxed by default for destructive operations.    │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  SOLVER                                              │
│  Single LLM call synthesizes all results.            │
│  Delivers the final answer.                          │
└──────────────────────────────────────────────────────┘
```

What this gives you: **3–5× token reduction** (batch observations instead of step-by-step), **full audit trail**, and **no surprises**.

## Quickstart

```bash
pip install rewoo
export ANTHROPIC_API_KEY=sk-ant-...

rewoo run "find all Python files modified today and summarize their changes"
```

You'll see:

```
📋 Execution Plan (4 steps)
─────────────────────────────────────────────────────
Step 1  [LOW]     shell.run   →  find . -name "*.py" -newer ...
Step 2  [LOW]     file.read   →  Read each found file
Step 3  [LOW]     web.search  →  (not needed, skipping)
Step 4  [LOW]     synthesize  →  Summarize changes

All steps are LOW risk. Proceeding automatically.
─────────────────────────────────────────────────────
✓ Step 1 complete (0.3s)
✓ Step 2 complete (0.1s)
✓ Step 4 complete (1.2s)

Result: Found 3 modified files. main.py: added error handling...
```

For high-risk operations:

```
📋 Execution Plan (3 steps)
─────────────────────────────────────────────────────
Step 1  [LOW]      shell.run   →  List files in /etc
Step 2  [HIGH]     shell.run   →  rm -rf /tmp/old_logs   ⚠️ Destructive
Step 3  [LOW]      shell.run   →  Verify deletion

⚠️  Step 2 requires approval.
Action: rm -rf /tmp/old_logs
This operation is irreversible.

Approve? [y/N/edit/skip]:
```

## Features

**Plan-first execution** — The full execution plan is generated before any tool call runs. No reactive surprises.

**Risk classification** — Every step is classified LOW / MEDIUM / HIGH / CRITICAL before you see it. Anything HIGH or above is gated on explicit approval.

**Immutable audit log** — Every plan, approval decision, execution result, and LLM call is recorded. In CLI mode via `~/.rewoo/audit.jsonl`, in production via PostgreSQL `audit_log` table.

**Sandboxed tools** — Shell commands run in subprocess sandboxes. File operations are path-restricted by default. Web requests respect a domain allowlist.

**Provider-agnostic** — Works with Anthropic (Claude), OpenAI (GPT-4o), or any OpenRouter model. Swap with `REWOO_MODEL=openai/gpt-4o`.

**Skill memory** — Learns patterns from successful executions and stores them as reusable skills.

**Production API** — FastAPI with JWT auth, API keys, rate limiting, WebSocket streaming, and OpenAPI docs.

**Distributed execution** — Celery workers with Redis broker for horizontal scaling.

**Full observability** — Prometheus metrics, structured JSON logging, OpenTelemetry tracing, health probes.

## How It Compares

| Feature | OpenClaw | Hermes | Paperclip | **ReWoo** |
|---|:---:|:---:|:---:|:---:|
| Plan before execute | ❌ | ❌ | ❌ | ✅ |
| Per-step risk classification | ❌ | ❌ | ❌ | ✅ |
| Approval gate for destructive actions | ❌ | ❌ | ❌ | ✅ |
| Immutable audit log | ❌ | Partial | ✅ | ✅ |
| Token-efficient (batch observations) | ❌ | ❌ | ❌ | ✅ 3–5× |
| Skill learning | ✅ | ✅ | ❌ | ✅ |
| Production API (auth, rate limiting) | ❌ | ❌ | ❌ | ✅ |
| Distributed task queue | ❌ | ❌ | ❌ | ✅ |
| Prometheus metrics | ❌ | ❌ | ❌ | ✅ |
| OpenTelemetry tracing | ❌ | ❌ | ❌ | ✅ |
| Kubernetes manifests + HPA | ❌ | ❌ | ❌ | ✅ |
| Python native | ❌ | ✅ | ❌ | ✅ |
| Self-hostable | ✅ | ✅ | ✅ | ✅ |

## Architecture

See [docs/architecture.md](./docs/architecture.md) for the full deep-dive.

The core modules:

- **`rewoo.core.planner`** — Prompts the LLM to produce a complete `ExecutionPlan` (list of `PlanStep` objects) without executing any tools.
- **`rewoo.core.worker`** — Executes individual `PlanStep` objects using the tool registry. Sandbox-enforced for destructive tools.
- **`rewoo.core.solver`** — Assembles all step results and makes a single LLM call to produce the final answer.
- **`rewoo.safety`** — Risk classifier, approval gate, and audit logger. These run between Planner and Worker.

The production stack:

- **`rewoo.api`** — FastAPI with 5 routers, JWT/API-key auth, rate limiting, WebSocket streaming
- **`rewoo.db`** — Async SQLAlchemy + PostgreSQL + Alembic migrations
- **`rewoo.cache`** — Redis for caching, rate limiting, and pub/sub
- **`rewoo.tasks`** — Celery distributed task queue
- **`rewoo.auth`** — JWT, bcrypt passwords, API key management
- **`rewoo.monitoring`** — Prometheus metrics, structured logging, OpenTelemetry, health checks

## REST API

ReWoo exposes a production REST API with full CRUD operations:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123", "name": "Alice"}'

# Login
curl -X POST http://localhost:8000/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'

# Create a plan
curl -X POST http://localhost:8000/api/v1/plans \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"task": "Summarize the last 5 git commits"}'

# Approve and execute
curl -X POST http://localhost:8000/api/v1/plans/<id>/approve \
  -H "Authorization: Bearer <token>" \
  -d '{"approvals": {"0": "approved", "1": "approved"}}'

# Execute
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Authorization: Bearer <token>" \
  -d '{"plan_id": "<plan-id>"}'

# Stream execution progress via WebSocket
wscat -c ws://localhost:8000/api/v1/executions/ws/<execution-id>
```

API docs available at `/api/docs` (Swagger) and `/api/redoc` (ReDoc).

## Production Deployment

### Docker Compose (Single Server)

```bash
cp .env.example .env
# Edit .env with your API keys and secure passwords
docker compose up -d
docker compose exec api alembic upgrade head
curl http://localhost:8000/api/health
```

### Kubernetes (Scalable Cluster)

```bash
# See docs/deployment-guide.md for full instructions
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets.yaml    # UPDATE VALUES FIRST!
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/ingress.yaml
```

Horizontal Pod Autoscalers scale API (3–50 replicas) and Workers (4–100 replicas) automatically.

## Installation

**From PyPI:**
```bash
pip install rewoo
```

**From source:**
```bash
git clone https://github.com/rewooai/rewoo.git
cd rewoo
make dev-install
```

**With production extras:**
```bash
pip install rewoo[otel]    # OpenTelemetry tracing
pip install rewoo[k8s]     # Kubernetes client
pip install rewoo[dev]     # Dev tools (pytest, ruff, mypy)
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Or set environment variables directly:

```bash
# LLM Provider
export ANTHROPIC_API_KEY=sk-ant-...
export REWOO_MODEL=claude-sonnet-4-6          # default

# Execution
export REWOO_APPROVAL_MODE=auto               # auto | cli | none
export REWOO_SANDBOX_ENABLED=true
export REWOO_AUDIT_PATH=~/.rewoo/audit.jsonl

# Production
export REWOO_DATABASE_URL=postgresql+asyncpg://rewoo:pass@localhost:5432/rewoo
export REWOO_REDIS_URL=redis://localhost:6379/0
export REWOO_JWT_SECRET=your-secure-random-secret
export REWOO_ENVIRONMENT=production
export REWOO_JSON_LOGS=true
export REWOO_RATE_LIMIT_ENABLED=true
```

See `.env.example` for the complete list of configuration options.

## CLI Reference

```bash
rewoo run "<task>"                # Run a task (plan → review → execute → solve)
rewoo plan "<task>"               # Show plan only, do not execute
rewoo audit                       # View recent audit log entries
rewoo skills                      # List learned skills
rewoo config                      # Show current configuration
rewoo doctor                      # Diagnose configuration issues
```

## Python SDK

```python
from rewoo import Agent
from rewoo.config import Settings

agent = Agent(settings=Settings(model="claude-sonnet-4-6"))

# Full run: plan → review → execute → solve
result = await agent.run("Summarize the last 5 git commits")
print(result.answer)
print(result.plan)        # Full ExecutionPlan
print(result.token_usage) # Tokens used across all LLM calls

# Plan only (no execution)
plan = await agent.plan("Delete all .pyc files recursively")
for step in plan.steps:
    print(f"[{step.risk_level}] {step.tool}: {step.description}")
```

## Roadmap

- [x] Core ReWOO Planner / Worker / Solver architecture
- [x] Risk classifier (LOW / MEDIUM / HIGH / CRITICAL)
- [x] CLI approval gate
- [x] Sandboxed shell and file tools
- [x] Immutable audit log
- [x] Anthropic + OpenAI providers
- [x] Skill memory (learn from successful executions)
- [x] FastAPI production API with auth and rate limiting
- [x] PostgreSQL + Alembic database persistence
- [x] Redis caching and pub/sub
- [x] Celery distributed task queue
- [x] JWT + API key authentication
- [x] Prometheus metrics and structured logging
- [x] OpenTelemetry distributed tracing
- [x] Docker multi-stage builds + docker-compose
- [x] Kubernetes manifests with HPA
- [x] CI/CD with GitHub Actions
- [ ] Web UI for plan management and audit visualization
- [ ] Telegram gateway
- [ ] Multi-agent orchestration
- [ ] Helm chart
- [ ] Terraform infrastructure modules

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). All contributions welcome — especially tool implementations, provider integrations, and safety improvements.

Quick start:
```bash
git clone https://github.com/rewooai/rewoo.git
cd rewoo
make dev-install
make test
```

## License

MIT © 2026 ReWoo Contributors

Built on the research of [ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models](https://arxiv.org/abs/2305.18323) (Xu et al., 2023).
