# Resilience-Antifragility Demonstration System

A multi-stage API demonstration system exploring resilience and antifragility patterns in cloud microservices. Built as part of a postgraduate research project on **adaptive self-healing cloud applications**.

The system runs four Flask APIs under identical chaos conditions, each representing a progressively more sophisticated resilience strategy. Metrics are collected via Prometheus and visualised in Grafana.

---

## System Architecture

| Service | Port | Strategy |
|---|---|---|
| Resilient API | 5002 | Circuit breaker + RL bandit + fallback chain |
| Baseline API | 5004 | Retries + circuit breaker, no AI/RL |
| Fragile API | 5003 | No retries, no fallbacks — fails under load |
| Adaptive API | 5005 | Function-specific chaos profiles + context-aware recovery |

Supporting services: Prometheus (9090), Grafana (3001), Loki (3100), Locust (8090).

---

## Prerequisites

- Docker and Docker Compose
- A [Groq](https://console.groq.com) API key (free tier is sufficient)
- An AWS EC2 instance (t2.medium or larger recommended) or any Linux host with 2GB+ RAM

---

## Quickstart

**1. Clone the repository**
```bash
git clone https://github.com/<your-username>/Resilience-Antifragility.git
cd Resilience-Antifragility
```

**2. Set your Groq API key**
```bash
cp .env.example .env
nano .env  # add your GROQ_API_KEY
```

**3. Free up space**
```bash
docker system prune -a --volumes -f
```

**4. (Recommended) Add a swap file if on a small instance**
```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

**5. Build**
```bash
docker compose build
```

**6. Train the RL agent**
```bash
docker compose run app python training/train_rl.py
```

**7. Start the system**
```bash
docker compose up
```

All services should be running within ~30 seconds. Check with:
```bash
docker compose ps
```

---

## Running Experiments

### Option A — Locust UI (recommended)
Open `http://<your-host>:8090`, set users and spawn rate, and point at `http://app:5002`.

### Option B — Chaos blast script
Fires structured chaos rounds (CPU, memory, network) across all APIs automatically:
```bash
bash scripts/chaos_blast.sh
```

### Option C — Endpoint test
Validates all API endpoints across a range of input values:
```bash
bash scripts/test_all_endpoints.sh
```

### Manual chaos injection
```bash
# CPU pressure
curl -X POST http://localhost:5002/chaos/cpu \
  -H "Content-Type: application/json" \
  -d '{"cores": 2, "seconds": 45}'

# Memory pressure
curl -X POST http://localhost:5002/chaos/memory \
  -H "Content-Type: application/json" \
  -d '{"mb": 80, "seconds": 60}'

# Reset all chaos
curl -X POST http://localhost:5002/chaos/reset
```

### Test Groq LLM endpoint
```bash
curl -X POST http://localhost:5002/ai/answer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "say hello"}'
```

---

## Observability

| Tool | URL | Credentials |
|---|---|---|
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Locust | http://localhost:8090 | — |

Grafana dashboards are provisioned automatically from `monitoring/grafana/dashboards/`.

---

## Experiment Configuration

Key parameters are set directly in the API files under `apis/`. The values used in experiments are:

| Parameter | Value |
|---|---|
| Stressor weights | none=0.40, latency=0.25, timeout=0.20, failure=0.15 |
| Circuit breaker threshold | 5 consecutive failures |
| Circuit breaker recovery timeout | 30s |
| SLO target success rate | 95% |
| SLO tracking window | 100 requests |
| LLM model | llama-3.1-8b-instant (Groq) |
| Resilient API memory limit | 512MB |
| Other APIs memory limit | 256MB each |

---

## Project Structure

```
├── apis/                   # All four Flask API services + shared modules
│   ├── app.py              # Resilient API
│   ├── fragile_api.py
│   ├── baseline_api.py
│   ├── adaptive_api.py
│   ├── metrics.py          # Shared Prometheus metrics
│   ├── learning.py         # RL training + chaos selector
│   └── feature_extraction.py
├── chaos/                  # Chaos module (bandit, policy manager, experiments)
├── monitoring/             # Prometheus, Grafana, Promtail config
├── load_testing/           # Locust load test file
├── training/               # RL agent training script
├── scripts/                # Test and chaos blast scripts
├── docker-compose.yml
├── dockerfile.app
├── dockerfile.locust.l
├── requirements.txt
└── .env.example
```
---

## Stopping the System

```bash
docker compose down
```

To also remove volumes:
```bash
docker compose down -v
```
