# ReWoo Architecture

## Overview

ReWoo implements the ReWOO (Reasoning Without Observations) architecture from the paper ["Decoupling Reasoning from Observations for Efficient Augmented Language Models"](https://arxiv.org/abs/2305.18323) (Xu et al., 2023).

The key insight of ReWoo is that planning and execution should be decoupled. Instead of the reactive loop used by most agent frameworks (reason -> act -> observe -> reason -> ...), ReWoo separates the process into four distinct stages, enabling plan-first execution with built-in safety guarantees.

## The Four Stages

### 1. Planner

The Planner generates a complete execution plan without making any tool calls. It uses the LLM to reason about the task and produce a structured list of steps, each identifying:

- **Tool** to use
- **Arguments** to pass
- **Dependencies** on other steps
- **Risk level** (assigned by the Risk Classifier after planning)

This is purely a reasoning step — no tools are invoked during planning. The Planner produces a JSON-structured plan that is parsed and validated into `PlanStep` objects. Robust JSON extraction handles various LLM response formats including markdown code blocks and malformed JSON.

### 2. Reviewer

The Reviewer sits between planning and execution as the critical safety gate. It:

- Displays the full execution plan to the user
- Classifies each step by risk level (LOW, MEDIUM, HIGH, CRITICAL)
- Requires explicit approval for HIGH and CRITICAL steps
- Allows the user to modify or reject individual steps
- Records all approval/rejection decisions in the audit log

This is the key safety innovation — users see exactly what will happen before it happens. Three approval modes are supported:

- **auto**: LOW/MEDIUM auto-approved, HIGH/CRITICAL approved with warning
- **cli**: Interactive approval via terminal prompts using Rich formatting
- **none**: All steps approved automatically (use with extreme caution)

### 3. Worker

The Worker executes each approved step in dependency order. It:

- Respects the dependency graph (steps only execute after their dependencies complete)
- Resolves context references (`{{step_N_output}}`) between steps
- Runs destructive tools in sandboxes (subprocess isolation, path restrictions, timeouts)
- Collects results for the Solver
- Handles failures gracefully without stopping the entire execution

The sandbox system blocks dangerous command patterns (rm -rf, sudo, curl|sh, mkfs, dd) and enforces path restrictions for file operations. High-risk and critical steps automatically trigger sandboxed execution.

### 4. Solver

The Solver takes all step results and makes a single LLM call to synthesize the final answer. This is the efficiency gain of ReWoo — instead of interleaving reasoning and observation across multiple turns, the Solver processes all evidence at once. Failed steps are included with their error messages, allowing the Solver to account for partial failures.

## Token Efficiency

The ReWoo architecture reduces token usage by 3-5x compared to reactive agent loops because:

1. **Batch observations:** The Solver sees all results at once, not one at a time
2. **No re-planning:** The Worker does not call the LLM between steps
3. **Single synthesis:** One LLM call replaces multiple reasoning turns
4. **No observation tokens:** The Planner generates steps without needing tool outputs

## Production Architecture

ReWoo is designed as a distributed system for production deployment at scale:

```
                    ┌──────────────────┐
                    │   Load Balancer  │
                    │  (nginx/ALB)     │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────┴─────┐ ┌────┴──────┐ ┌─────┴─────┐
        │  API Pod   │ │  API Pod  │ │  API Pod  │
        │ (FastAPI)  │ │ (FastAPI) │ │ (FastAPI) │
        └─────┬──────┘ └────┬──────┘ └─────┬─────┘
              │              │              │
              └──────┬───────┴──────────────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
    ┌─────┴───┐ ┌───┴────┐ ┌──┴──────┐
    │ Redis   │ │ Redis  │ │ Redis   │
    │ Cache   │ │ Rate   │ │ Pub/Sub │
    │         │ │ Limit  │ │         │
    └─────────┘ └────────┘ └─────────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
    ┌─────┴─────┐ ┌─┴───────┐ ┌┴────────┐
    │ Worker    │ │ Worker  │ │ Worker  │
    │ (Celery)  │ │ (Celery)│ │ (Celery)│
    └─────┬─────┘ └─┬───────┘ └┬────────┘
          │          │          │
          └──────────┼──────────┘
                     │
              ┌──────┴───────┐
              │  PostgreSQL  │
              │  (Primary)   │
              └──────────────┘
```

### Component Responsibilities

| Component | Technology | Role |
|-----------|-----------|------|
| API Server | FastAPI + Uvicorn | HTTP/WebSocket, auth, rate limiting |
| Workers | Celery + Redis | Asynchronous plan execution |
| Beat | Celery Beat | Periodic tasks (cleanup, monitoring) |
| PostgreSQL | 16 + asyncpg | Users, plans, executions, audit log |
| Redis | 7 + aioredis | Cache, rate limiting, pub/sub, broker |

### Data Flow

1. **Request arrives** at API server through load balancer
2. **Auth middleware** validates JWT/API key and sets user context
3. **Rate limiter** checks Redis sliding window for the user's tier
4. **Plan creation** calls the LLM, classifies risk, stores in PostgreSQL
5. **Approval** updates step statuses in the database
6. **Execution** enqueues a Celery task, returns immediately with 202
7. **Worker** picks up the task, runs the full Planner-Reviewer-Worker-Solver cycle
8. **Progress** streamed via Redis pub/sub to WebSocket clients
9. **Result** stored in PostgreSQL, published to Redis

## Safety Architecture

### Risk Classifier

The Risk Classifier uses a multi-signal approach:

1. **Tool-level defaults:** Each tool has a default risk level (shell.run = MEDIUM, file.delete = HIGH, web.search = LOW)
2. **Argument pattern matching:** Regular expressions detect destructive patterns (rm -rf, sudo, curl|sh, dd, mkfs, chmod 777)
3. **Description analysis:** Natural language descriptions are scanned for risk indicators
4. **Reversibility assessment:** Destructive operations are marked as irreversible — this propagates through the system so the approval gate can warn users

### Approval Gates

Three approval modes are supported:

- **auto:** LOW/MEDIUM auto-approved, HIGH/CRITICAL approved with warning
- **cli:** Interactive approval via terminal prompts (Rich-formatted)
- **none:** All steps approved automatically (use with caution)

### Sandboxed Execution

The sandbox system provides multiple layers of protection:

- **Blocked patterns:** Dangerous commands are blocked outright (rm -rf /, dd, mkfs, curl|sh)
- **Path restrictions:** File operations are confined to allowed directories
- **Timeout enforcement:** All commands have configurable timeouts (default 300s)
- **Subprocess isolation:** Commands run in separate processes, not the main Python process

### Audit Trail

Every execution event is recorded immutably:

- **CLI mode:** Append-only JSONL file at `~/.rewoo/audit.jsonl`
- **Production mode:** PostgreSQL `audit_log` table with UUIDs, timestamps, and JSON data
- **Events logged:** Plan creation, step approval/rejection, step execution, final synthesis

This enables full reconstruction of any execution for debugging, compliance, or forensic analysis.

## Module Organization

```
rewoo/
├── core/              # ReWOO architecture — the innovation
│   ├── types.py       # Pydantic models (RiskLevel, PlanStep, ExecutionPlan, etc.)
│   ├── planner.py     # Generates execution plans via LLM
│   ├── worker.py      # Executes approved steps in dependency order
│   ├── solver.py      # Synthesizes final answers from all step results
│   └── reviewer.py    # Review gate coordination (approval + audit)
├── safety/            # The core differentiator
│   ├── risk_classifier.py  # Multi-signal risk classification
│   ├── approval_gate.py    # CLI, Auto, and None approval modes
│   └── audit.py            # Immutable audit logging (JSONL + DB)
├── tools/             # Tool registry and execution
│   ├── registry.py    # Tool registration, lookup, defaults
│   ├── sandbox.py     # Sandboxed subprocess execution
│   └── builtin/       # Built-in tools (shell, file, web)
├── providers/         # LLM abstraction layer
│   ├── base.py        # BaseProvider ABC
│   ├── anthropic.py   # Claude models
│   └── openai.py      # GPT models + OpenRouter
├── agent/             # Agent orchestration
│   ├── loop.py        # Full Plan→Review→Execute→Solve cycle
│   ├── memory.py      # Skill learning and persistence
│   └── state.py       # Execution state tracking
├── api/               # Production REST API
│   ├── app.py         # FastAPI application factory
│   ├── routers/       # Endpoint handlers (health, users, plans, executions, skills)
│   └── middleware/     # Auth, rate limiting, request ID
├── db/                # Database layer
│   ├── models.py      # SQLAlchemy ORM models
│   ├── session.py     # Async session management
│   └── migrations/    # Alembic migrations
├── auth/              # Authentication
│   ├── jwt.py         # JWT token creation/verification
│   ├── passwords.py   # bcrypt password hashing
│   └── api_keys.py    # API key verification
├── cache/             # Caching layer
│   └── redis.py       # Redis connection pool + CacheManager
├── tasks/             # Distributed task execution
│   └── executor.py    # Celery task for plan execution
├── monitoring/        # Observability
│   ├── metrics.py     # Prometheus metrics
│   ├── logging.py     # Structured JSON/dev logging
│   ├── health.py      # Health check utilities
│   └── tracing.py     # OpenTelemetry distributed tracing
├── gateway/           # Multi-channel input
│   ├── base.py        # BaseGateway ABC
│   └── cli.py         # CLI gateway (Rich-formatted)
├── config.py          # Pydantic Settings with env var support
├── constants.py       # Default paths, risk levels, statuses
└── cli.py             # Click CLI with Rich output
```

## Database Schema

```
users               api_keys            execution_plans
┌──────────────┐   ┌──────────────┐    ┌──────────────┐
│ id (UUID)     │──│ user_id (FK) │───│ user_id (FK) │
│ email         │   │ name         │    │ task         │
│ password_hash │   │ key_hash     │    │ steps_data   │
│ name          │   │ key_prefix   │    │ has_high_risk│
│ tier          │   │ tier         │    │ status       │
│ is_active     │   │ is_active    │    │ total_tokens │
│ created_at    │   │ last_used    │    │ created_at   │
│ updated_at    │   │ created_at   │    │ updated_at   │
└──────────────┘   └──────────────┘    └──────────────┘

executions          skills              audit_log
┌──────────────┐   ┌──────────────┐    ┌──────────────┐
│ id (UUID)     │   │ id (UUID)     │    │ id (UUID)     │
│ plan_id (FK)  │   │ user_id (FK) │    │ event_type   │
│ user_id (FK)  │   │ name         │    │ user_id (FK) │
│ task          │   │ description  │    │ plan_id      │
│ status        │   │ task_pattern │    │ execution_id │
│ answer        │   │ plan_template│    │ step_index   │
│ step_results  │   │ use_count    │    │ data (JSON)  │
│ total_tokens  │   │ success_count│    │ timestamp    │
│ duration      │   │ last_used    │    └──────────────┘
│ error_message │   │ created_at   │
│ created_at    │   └──────────────┘
│ completed_at  │
└──────────────┘
```

## Scaling Strategy

### Horizontal Scaling

- **API servers:** Stateless — scale with HPA based on CPU (3-50 replicas)
- **Workers:** Stateless — scale with HPA based on CPU and queue depth (4-100 replicas)
- **PostgreSQL:** Vertical scaling + read replicas for heavy read workloads
- **Redis:** Redis Cluster for sharding at very high throughput

### Rate Limiting

Sliding window rate limiting per user tier:

| Tier | Rate Limit | Burst |
|------|-----------|-------|
| Anonymous | 20/min | 30 |
| Free | 60/min | 100 |
| Pro | 300/min | 500 |
| Enterprise | 3,000/min | 5,000 |

### Observability Stack

- **Metrics:** Prometheus scrapes `/api/metrics` every 15s
- **Tracing:** OpenTelemetry OTLP exporter to Jaeger/Tempo
- **Logging:** JSON structured logs → ELK/Loki/Datadog
- **Alerting:** Alertmanager rules on error rates, latency, and queue depth
