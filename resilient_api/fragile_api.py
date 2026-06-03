from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import random
import time
import logging
import threading
from pythonjsonlogger import jsonlogger
import psutil
import threading
from collections import deque
import time

app = Flask(__name__)

API_SLO_ADHERENCE = Gauge(
    "api_slo_adherence_ratio",
    "Ratio of requests meeting all SLOs in the rolling window",
    ["stage"]
)


# -----------------------------------------------------------------------
# SLO thresholds — edit these to match your targets
# -----------------------------------------------------------------------
SLO_LATENCY_MS      = 1000   # p95 target: requests must complete under 1s
SLO_ERROR_RATE      = 0.10   # no more than 10% errors in the rolling window
SLO_WINDOW_SIZE     = 100    # rolling window: last N requests per stage
 
# -----------------------------------------------------------------------
# Per-stage rolling windows  { stage: deque of bools (True = met SLO) }
# Each entry is True if that request met ALL SLOs, False otherwise.
# -----------------------------------------------------------------------
_slo_windows = {
    "resilient":  deque(maxlen=SLO_WINDOW_SIZE),
    "baseline":   deque(maxlen=SLO_WINDOW_SIZE),
    "naive":      deque(maxlen=SLO_WINDOW_SIZE),
    "reactive":   deque(maxlen=SLO_WINDOW_SIZE),
    "fragile":    deque(maxlen=SLO_WINDOW_SIZE),
    "antifragile": deque(maxlen=SLO_WINDOW_SIZE),
}
_slo_lock = threading.Lock()

# -----------------------------------------------------------------------
# CPU & Memory Share
# -----------------------------------------------------------------------
FRAGILE_CPU_SHARE = Gauge("fragile_cpu_share", "Fragile share of total CPU")
FRAGILE_MEMORY_SHARE = Gauge("fragile_memory_share", "Fragile share of total Memory")

def update_fragile_metrics():
    proc = psutil.Process()
    while True:
        cpu_share = proc.cpu_percent(interval=1) / psutil.cpu_count()
        mem_share = proc.memory_percent()
        FRAGILE_CPU_SHARE.set(cpu_share)
        FRAGILE_MEMORY_SHARE.set(mem_share)

threading.Thread(target=update_fragile_metrics, daemon=True).start()

# -----------------------------------------------------------------------
# Prometheus Metrics
# -----------------------------------------------------------------------
# Stage-unified counters — same metric names as resilient_api so the
# "Request rate by stage" and "Success rate by stage" dashboard panels
# automatically include the fragile stage.
from prometheus_client import Counter as _Counter
try:
    from metrics import api_requests_total, api_errors_total
except Exception:
    # Fallback if metrics module not available — define locally.
    api_requests_total = _Counter(
        "api_requests_total",
        "Total requests per stage",
        ["stage"]
    )
    api_errors_total = _Counter(
        "api_errors_total",
        "Total errors per stage",
        ["stage"]
    )

# Fragile-specific metrics
FRAGILE_REQUESTS = Counter("fragile_requests_total", "Total requests to fragile API", ["stage"])
FRAGILE_ERRORS   = Counter("fragile_errors_total",   "Total errors from fragile API",  ["reason"])
FRAGILE_LATENCY  = Histogram("fragile_latency_seconds", "Latency of fragile API responses")

logger = logging.getLogger("fragile_logger")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)

# -----------------------------------------------------------------------
# Failure modes and their probabilities
# -----------------------------------------------------------------------
FAILURE_MODES = {
    "immediate_500":  0.30,   # instant server error
    "slow_timeout":   0.30,   # 3-6 s delay then error
    "random_latency": 0.20,   # 1-3 s extra latency but succeeds
    "success":        0.20,   # normal response
}


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/fragile-api/process", methods=["POST"])
def fragile_process():
    # ---- count the request immediately (before any chaos) ----
    FRAGILE_REQUESTS.labels(stage="fragile").inc()
    api_requests_total.labels(stage="fragile").inc()   # <-- feeds stage comparison panels

    start = time.time()

    data  = request.get_json(force=True) or {}
    value = data.get("value", 1.0)

    # Pick a failure mode
    roll       = random.random()
    cumulative = 0.0
    mode       = "success"
    for name, prob in FAILURE_MODES.items():
        cumulative += prob
        if roll < cumulative:
            mode = name
            break

    if mode == "immediate_500":
        FRAGILE_ERRORS.labels(reason="server_error").inc()
        api_errors_total.labels(stage="fragile").inc()   # <-- feeds error-rate panel
        FRAGILE_LATENCY.observe(time.time() - start)
        logger.error("Fragile API: immediate failure", extra={"value": value, "mode": mode})
        record_slo("fragile", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "fragile", "error": "Internal server error"}), 500

    elif mode == "slow_timeout":
        delay = random.uniform(3.0, 6.0)
        time.sleep(delay)
        FRAGILE_ERRORS.labels(reason="latency").inc()
        api_errors_total.labels(stage="fragile").inc()
        FRAGILE_LATENCY.observe(time.time() - start)
        logger.error("Fragile API: slow timeout", extra={"value": value, "delay": delay})
        record_slo("fragile", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "fragile", "error": "Too slow"}), 504

    elif mode == "random_latency":
        delay = random.uniform(1.0, 3.0)
        time.sleep(delay)
        result = value * 2
        FRAGILE_LATENCY.observe(time.time() - start)
        logger.info("Fragile API: slow success", extra={"value": value, "delay": delay})
        record_slo("fragile", (time.time() - start) * 1000, success=True)
        return jsonify({"stage": "fragile", "result": result, "latency_injected": delay}), 200

    else:
        # Normal success — small base latency
        time.sleep(random.uniform(0.05, 0.2))
        result = value * 2
        FRAGILE_LATENCY.observe(time.time() - start)
        logger.info("Fragile API: success", extra={"value": value})
        record_slo("fragile", (time.time() - start) * 1000, success=True)
        return jsonify({"stage": "fragile", "result": result}), 200


@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/metrics': make_wsgi_app()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=False, use_reloader=False)