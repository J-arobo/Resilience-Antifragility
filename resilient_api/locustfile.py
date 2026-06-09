"""
locustfile.py
========================
Merged locust file: existing steady traffic + chaos ramp orchestrator.

HOW TO RUN
----------
Option A — Locust web UI (recommended, you can watch it live):
    locust -f locustfile_chaos_ramp.py
    Then open http://localhost:8089
    Set users=40, spawn rate=5, host=http://app:5002
    Click Start — watch Grafana alongside it.

Option B — headless, 5 min ramp test, HTML report:
    locust -f locustfile_chaos_ramp.py \
      --headless -u 40 -r 5 --run-time 300s \
      --host http://app:5002 \
      --html chaos_ramp_report.html

WHAT HAPPENS (timeline)
-----------------------
  t=0s   — Normal + Burst traffic starts immediately
  t=30s  — Light chaos: 1 CPU core for 20s, 32MB RAM for 30s
  t=60s  — Moderate: 2 cores/30s, 48MB/40s
  t=90s  — Sustained: 2 cores/45s, 64MB/60s
  t=120s — Heavy: 3 cores/60s, 64MB/60s  <- Baseline starts cracking here
  t=150s — Peak sustained: 3 cores/60s, 72MB/60s
  t=180s — Spike: 4 cores/45s, 80MB/45s  <- Circuit breaker opens here
  t=210s — Recovery ramp-down: 2 cores/30s, 48MB/30s
  t=240s — Tail: 1 core/20s, 32MB/20s
  t=300s — Test ends, /chaos/reset fires automatically

WATCHING IT
-----------
  Locust UI  -> http://localhost:8089
  Grafana    -> http://localhost:3001
    - Set time range: Last 10 minutes, auto-refresh: 5s
    - Watch: Chaos Ramp section first, then error rate, then SLO adherence

DOCKER NETWORK NOTES
--------------------
  CHAOS_HOST   = http://app:5002        (resilient API + /chaos/* owner)
  FRAGILE_HOST = http://fragile-api:5003
  BASELINE_HOST= http://baseline-api:5004
  ADAPTIVE_HOST= http://adaptive-api:5005
  Adjust these constants if your docker-compose service names differ.
"""

import random
import time
import threading
from locust import HttpUser, TaskSet, task, between, events

# ---------------------------------------------------------------------------
# Service base URLs 
# ---------------------------------------------------------------------------
CHAOS_HOST    = "http://app:5002"
FRAGILE_HOST  = "http://fragile-api:5003"
BASELINE_HOST = "http://baseline-api:5004"
ADAPTIVE_HOST = "http://adaptive-api:5005"

# ---------------------------------------------------------------------------
# Chaos ramp schedule
# (seconds_since_start, cpu_cores, cpu_seconds, memory_mb, memory_seconds)
# ---------------------------------------------------------------------------
CHAOS_SCHEDULE = [
    (30,  1, 20,  32, 30),
    (60,  2, 30,  48, 40),
    (90,  2, 45,  64, 60),
    (120, 3, 60,  64, 60),
    (150, 3, 60,  72, 60),
    (180, 4, 45,  80, 45),
    (210, 2, 30,  48, 30),
    (240, 1, 20,  32, 20),
]

_chaos_lock      = threading.Lock()
_fired_events    = set()
_test_start_time = None


def random_payload():
    return {"value": random.choice([10, 0, -5, 1.5, 7777777])}


# ---------------------------------------------------------------------------
# Chaos Orchestrator
# ---------------------------------------------------------------------------
class ChaosOrchestratorTasks(TaskSet):

    def on_start(self):
        global _test_start_time
        with _chaos_lock:
            if _test_start_time is None:
                _test_start_time = time.time()
                print("\n[CHAOS] Orchestrator ready — ramp schedule armed")

    @task(10)
    def maybe_fire_chaos(self):
        global _test_start_time
        if _test_start_time is None:
            time.sleep(1)
            return

        elapsed = time.time() - _test_start_time

        for entry in CHAOS_SCHEDULE:
            t_start, cpu_cores, cpu_dur, mem_mb, mem_dur = entry
            if elapsed >= t_start and t_start not in _fired_events:
                with _chaos_lock:
                    if t_start not in _fired_events:
                        _fired_events.add(t_start)

                print(f"\n[CHAOS] t={elapsed:.0f}s  ->  "
                      f"CPU {cpu_cores}x{cpu_dur}s  |  MEM {mem_mb}MB/{mem_dur}s")

                try:
                    with self.client.post(
                        "/chaos/cpu",
                        json={"cores": cpu_cores, "seconds": cpu_dur},
                        name="/chaos/cpu",
                        catch_response=True
                    ) as r:
                        r.success()
                except Exception as exc:
                    print(f"[CHAOS] CPU error: {exc}")

                time.sleep(0.15)

                try:
                    with self.client.post(
                        "/chaos/memory",
                        json={"mb": mem_mb, "seconds": mem_dur},
                        name="/chaos/memory",
                        catch_response=True
                    ) as r:
                        r.success()
                except Exception as exc:
                    print(f"[CHAOS] MEM error: {exc}")

        time.sleep(2)

    @task(1)
    def health_ping(self):
        with self.client.get(
            "/health",
            name="/health (orchestrator)",
            catch_response=True
        ) as r:
            r.success()
        time.sleep(5)


class ChaosOrchestrator(HttpUser):
    host      = CHAOS_HOST
    tasks     = [ChaosOrchestratorTasks]
    wait_time = between(1, 2)
    weight    = 1


# ---------------------------------------------------------------------------
# Your existing traffic user — unchanged logic, Docker hostnames preserved
# ---------------------------------------------------------------------------
class ResilientUser(HttpUser):
    wait_time = between(0.5, 3)
    host      = CHAOS_HOST
    weight    = 3

    @task(3)
    def post_resilient(self):
        self.client.post(
            "/resilient-api/process",
            json=random_payload(),
            name="Resilient API"
        )

    @task(2)
    def post_baseline(self):
        with self.client.rename_request("/baseline-api/process"):
            self.client.post(
                f"{BASELINE_HOST}/baseline-api/process",
                json=random_payload(),
                name="Baseline API"
            )

    @task(2)
    def post_fragile(self):
        with self.client.rename_request("/fragile-api/process"):
            self.client.post(
                f"{FRAGILE_HOST}/fragile-api/process",
                json=random_payload(),
                name="Fragile API"
            )

    @task(2)
    def adaptive_data_processing(self):
        with self.client.rename_request("/adaptive-api/process"):
            self.client.post(
                f"{ADAPTIVE_HOST}/adaptive-api/process",
                json={"value": random.choice([10, 0, -5, 1.5, 100]),
                      "function_type": "data_processing"},
                name="Adaptive API - data_processing"
            )

    @task(2)
    def adaptive_llm_inference(self):
        with self.client.rename_request("/adaptive-api/process"):
            self.client.post(
                f"{ADAPTIVE_HOST}/adaptive-api/process",
                json={"value": random.choice([1, 5, 10, 50]),
                      "function_type": "llm_inference"},
                name="Adaptive API - llm_inference"
            )

    @task(2)
    def adaptive_realtime_query(self):
        with self.client.rename_request("/adaptive-api/process"):
            self.client.post(
                f"{ADAPTIVE_HOST}/adaptive-api/process",
                json={"value": random.choice([1, 2, 3, 5, 7]),
                      "function_type": "realtime_query"},
                name="Adaptive API - realtime_query"
            )

    @task(1)
    def adaptive_profile(self):
        with self.client.rename_request("/adaptive-api/profile"):
            self.client.get(
                f"{ADAPTIVE_HOST}/adaptive-api/profile",
                name="Adaptive API - profile check"
            )


# ---------------------------------------------------------------------------
# Burst user — pressures Resilient + Fragile during chaos peak
# ---------------------------------------------------------------------------
class BurstUser(HttpUser):
    wait_time = between(0.1, 0.5)
    host      = CHAOS_HOST
    weight    = 2

    @task(5)
    def burst_resilient(self):
        with self.client.post(
            "/resilient-api/process",
            json=random_payload(),
            name="Resilient API",
            catch_response=True
        ) as r:
            if r.status_code in (200, 503):
                r.success()

    @task(3)
    def burst_fragile(self):
        with self.client.rename_request("/fragile-api/process"):
            with self.client.post(
                f"{FRAGILE_HOST}/fragile-api/process",
                json=random_payload(),
                name="Fragile API",
                catch_response=True
            ) as r:
                r.success()

    @task(2)
    def burst_baseline(self):
        with self.client.rename_request("/baseline-api/process"):
            with self.client.post(
                f"{BASELINE_HOST}/baseline-api/process",
                json=random_payload(),
                name="Baseline API",
                catch_response=True
            ) as r:
                r.success()


# ---------------------------------------------------------------------------
# Auto-reset chaos at end of test
# ---------------------------------------------------------------------------
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    import requests as req
    try:
        resp = req.post(f"{CHAOS_HOST}/chaos/reset", timeout=5)
        print(f"\n[CHAOS] Reset -> HTTP {resp.status_code}")
    except Exception as exc:
        print(f"\n[CHAOS] Reset failed: {exc}")
    _fired_events.clear()
    global _test_start_time
    _test_start_time = None


@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               response, context, exception, **kwargs):
    if "/chaos/" in (name or "") and exception is None:
        status = getattr(response, "status_code", "?")
        print(f"[CHAOS EVENT] {name} -> HTTP {status} ({response_time:.0f}ms)")