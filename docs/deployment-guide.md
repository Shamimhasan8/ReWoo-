# ReWoo Production Deployment Guide

## Architecture Overview

ReWoo is designed as a distributed system with these components:

- **API Server** (FastAPI + Uvicorn) — Handles HTTP/WebSocket requests
- **Worker** (Celery) — Executes plans asynchronously
- **Beat** (Celery Beat) — Periodic task scheduler
- **PostgreSQL** — Primary database for users, plans, executions
- **Redis** — Caching, rate limiting, pub/sub, and Celery broker

## Quick Start (Docker Compose)

1. Clone the repository:
   ```bash
   git clone https://github.com/rewooai/rewoo.git
   cd rewoo
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and passwords
   ```

3. Start all services:
   ```bash
   docker compose up -d
   ```

4. Run database migrations:
   ```bash
   docker compose exec api alembic upgrade head
   ```

5. Verify the deployment:
   ```bash
   curl http://localhost:8000/api/health
   ```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.28+)
- kubectl configured
- Helm 3 (optional)
- cert-manager (for TLS)
- nginx-ingress controller

### Deploy

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (UPDATE VALUES FIRST!)
# Edit k8s/secrets.yaml with production values
kubectl apply -f k8s/secrets.yaml

# Deploy PostgreSQL
kubectl apply -f k8s/postgres.yaml

# Deploy Redis
kubectl apply -f k8s/redis.yaml

# Wait for database to be ready
kubectl wait --for=condition=ready pod -l app=rewoo-postgres -n rewoo --timeout=120s

# Deploy API server
kubectl apply -f k8s/api-deployment.yaml

# Deploy workers
kubectl apply -f k8s/worker-deployment.yaml

# Deploy ingress
kubectl apply -f k8s/ingress.yaml

# Run migrations
kubectl exec -it deployment/rewoo-api -n rewoo -- alembic upgrade head
```

### Verify

```bash
# Check pod status
kubectl get pods -n rewoo

# Check API health
kubectl port-forward svc/rewoo-api 8000:8000 -n rewoo &
curl http://localhost:8000/api/health

# Check HPA status
kubectl get hpa -n rewoo
```

### Scaling

The API and Worker deployments use Horizontal Pod Autoscalers:

| Component | Min | Max | Scale Trigger |
|-----------|-----|-----|---------------|
| API | 3 | 50 | CPU > 70% |
| Worker | 4 | 100 | CPU > 60% |

Manual scaling:
```bash
kubectl scale deployment rewoo-api --replicas=10 -n rewoo
kubectl scale deployment rewoo-worker --replicas=20 -n rewoo
```

## Monitoring

### Health Endpoints

- `GET /api/health` — Liveness probe
- `GET /api/ready` — Readiness probe (checks DB + Redis)
- `GET /api/metrics` — Prometheus metrics

### Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `rewoo_requests_total` | Counter | Total API requests by method/endpoint/status |
| `rewoo_request_duration_seconds` | Histogram | Request latency distribution |
| `rewoo_executions_total` | Counter | Total plan executions by status |
| `rewoo_execution_duration_seconds` | Histogram | Execution time distribution |
| `rewoo_tokens_total` | Counter | LLM token usage by model/type |
| `rewoo_active_executions` | Gauge | Currently running executions |

### Grafana Dashboard

Import the ReWoo dashboard (ID: TBD) for:
- Request rate and latency percentiles
- Execution success/failure rates
- Token usage over time
- Database connection pool status
- Redis operation rates

### Logging

Production uses JSON structured logs:
```json
{
  "timestamp": "2026-06-11T12:00:00Z",
  "level": "INFO",
  "logger": "rewoo.api.routers.plans",
  "message": "Plan created",
  "request_id": "abc123",
  "user_id": "uuid-here",
  "plan_id": "plan-uuid"
}
```

## Load Testing

```bash
# Install locust
pip install locust

# Run load test (1,000 users, 100/s ramp)
locust -f tests/load/locustfile.py \
  --host=http://your-api-url \
  --users=1000 \
  --spawn-rate=100 \
  --run-time=5m
```

## Troubleshooting

### Database Connection Issues
```bash
# Check database connectivity
kubectl exec -it deployment/rewoo-api -n rewoo -- python -c "
from rewoo.db.session import init_db, get_db_session
import asyncio
async def check():
    await init_db()
    async with get_db_session() as s:
        r = await s.execute('SELECT 1')
        print('DB OK:', r.scalar())
asyncio.run(check())
"
```

### Redis Issues
```bash
# Check Redis connectivity
kubectl exec -it deployment/rewoo-api -n rewoo -- python -c "
import asyncio, redis.asyncio as aioredis
async def check():
    r = aioredis.from_url('redis://rewoo-redis:6379/0')
    print('Redis PING:', await r.ping())
asyncio.run(check())
"
```

### Worker Not Processing Tasks
```bash
# Check Celery worker status
kubectl logs deployment/rewoo-worker -n rewoo --tail=50

# Check Redis queue length
kubectl exec -it deployment/rewoo-redis -n rewoo -- redis-cli LLEN celery
```
