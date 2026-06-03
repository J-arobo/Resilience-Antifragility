from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import random
import time
import logging
import threading
from pythonjsonlogger import jsonlogger
from enum import Enum
import psutil
from metrics import api_requests_total, api_errors_total
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
# Prometheus Metrics
# -----------------------------------------------------------------------
# Stage-unified counters — same metric names as resilient_api so the
# "Request rate by stage", "Success rate by stage" and error-rate panels
# automatically include the baseline stage.
from prometheus_client import Counter as _Counter
try:
    from metrics import api_requests_total, api_errors_total
except Exception:
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

BASELINE_LATENCY        = Histogram("baseline_latency_seconds",    "Latency of baseline API responses")
BASELINE_RETRIES        = Counter("baseline_retry_total",          "Total retry attempts by baseline API")
BASELINE_CIRCUIT_BREAKER = Gauge("baseline_circuit_breaker_open", "Circuit breaker state (1=open)")
BASELINE_CPU            = Gauge("baseline_cpu_percent",            "CPU usage of baseline API")
BASELINE_MEMORY         = Gauge("baseline_memory_percent",         "Memory usage of baseline API")
BASELINE_REQUESTS = Counter("baseline_requests_total", "Baseline requests", ["stage"])
BASELINE_ERRORS   = Counter("baseline_errors_total",   "Baseline errors",   ["stage"])


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
    "baseline":   deque(maxlen=SLO_WINDOW_SIZE)
}
_slo_lock = threading.Lock()



# Fallback-equivalent counter so "Fallback usage" panel can include baseline
BASELINE_FALLBACK = Counter(
    "baseline_fallback_total",
    "Baseline requests that exhausted all retries (proxy for fallback)",
    ["reason"]
)

logger = logging.getLogger("baseline_logger")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)

# -----------------------------------------------------------------------
# Circuit Breaker (simple, no RL)
# -----------------------------------------------------------------------
class CircuitState(Enum):
    CLOSED   = "closed"
    OPEN     = "open"
    HALF_OPEN = "half_open"

CB_STATE        = CircuitState.CLOSED
CB_FAILURES     = 0
CB_LAST_FAILURE = 0
CB_THRESHOLD    = 3
CB_COOLDOWN     = 10
CB_LOCK         = threading.Lock()


def cb_is_open() -> bool:
    global CB_STATE, CB_LAST_FAILURE
    with CB_LOCK:
        if CB_STATE == CircuitState.OPEN:
            if time.time() - CB_LAST_FAILURE > CB_COOLDOWN:
                CB_STATE = CircuitState.HALF_OPEN
                return False
            return True
        return False


def cb_record_success():
    global CB_STATE, CB_FAILURES
    with CB_LOCK:
        CB_FAILURES = 0
        CB_STATE    = CircuitState.CLOSED
        BASELINE_CIRCUIT_BREAKER.set(0)


def cb_record_failure():
    global CB_STATE, CB_FAILURES, CB_LAST_FAILURE
    with CB_LOCK:
        CB_FAILURES    += 1
        CB_LAST_FAILURE = time.time()
        if CB_FAILURES >= CB_THRESHOLD:
            CB_STATE = CircuitState.OPEN
            BASELINE_CIRCUIT_BREAKER.set(1)
            logger.warning("Baseline circuit breaker opened")


# -----------------------------------------------------------------------
# Stressor injection — same probabilities as resilient API, no AI
# -----------------------------------------------------------------------
STRESSOR_WEIGHTS = {
    "none":    0.55,  #65% of attempts succeeded
    "latency": 0.20,  # latency fails but still succeed
    "timeout": 0.15,  # hard failure
    "failure": 0.10,  # hard failure
}

MAX_RETRIES = 3

def inject_stressor(value):
    stressor = random.choices(
        list(STRESSOR_WEIGHTS.keys()),
        weights=list(STRESSOR_WEIGHTS.values())
    )[0]

    if stressor == "timeout":
        raise TimeoutError("Simulated timeout")

    elif stressor == "latency":
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)
        return value * 2

    elif stressor == "failure":
        raise Exception("Simulated failure")

    else:
        time.sleep(random.uniform(0.05, 0.2))
        return value * 2


# -----------------------------------------------------------------------
# Simple retry (no tenacity, no RL arm selection)
# -----------------------------------------------------------------------
MAX_RETRIES = 3

def process_with_retry(value):
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            result = inject_stressor(value)
            cb_record_success()
            return result, attempt + 1
        except TimeoutError as e:
            last_exc = e
            BASELINE_RETRIES.inc()
            # Don't count retries as errors — only final failure is an error
            time.sleep(0.5)
        except Exception as e:
            last_exc = e
            BASELINE_RETRIES.inc()
            time.sleep(0.3)
    cb_record_failure()
    raise last_exc

# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/baseline-api/process", methods=["POST"])
def baseline_process():
    # ---- count the request immediately ----
    BASELINE_REQUESTS.labels(stage="baseline").inc()
    api_requests_total.labels(stage="baseline").inc()   # <-- stage comparison panels

    start = time.time()

    proc = psutil.Process()
    BASELINE_CPU.set(proc.cpu_percent(interval=0.1))
    BASELINE_MEMORY.set(proc.memory_percent())

    data  = request.get_json(force=True) or {}
    value = data.get("value", 1.0)

    if value is None or not isinstance(value, (int, float)):
        BASELINE_ERRORS.labels(reason="invalid_input").inc()
        api_errors_total.labels(stage="baseline").inc()
        BASELINE_LATENCY.observe(time.time() - start)
        return jsonify({"error": "Invalid input"}), 400

    if cb_is_open():
        BASELINE_ERRORS.labels(reason="circuit_open").inc()
        api_errors_total.labels(stage="baseline").inc()
        BASELINE_FALLBACK.labels(reason="circuit_breaker_open").inc()
        BASELINE_LATENCY.observe(time.time() - start)
        logger.warning("Baseline: circuit breaker open, rejecting request")
        record_slo("baseline", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "baseline", "error": "Circuit breaker open"}), 503

    try:
        result, attempts = process_with_retry(value)
        BASELINE_LATENCY.observe(time.time() - start)
        logger.info("Baseline: success", extra={"result": result, "attempts": attempts})
        record_slo("baseline", (time.time() - start) * 1000, success=True)
        return jsonify({
            "stage":           "baseline",
            "result":          result,
            "attempts":        attempts,
            "circuit_breaker": "closed"
        }), 200

    except TimeoutError as e:
        BASELINE_ERRORS.labels(reason="timeout").inc()
        api_errors_total.labels(stage="baseline").inc()
        BASELINE_FALLBACK.labels(reason="timeout_exhausted").inc()
        BASELINE_LATENCY.observe(time.time() - start)
        record_slo("baseline", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "baseline", "error": str(e)}), 504

    except Exception as e:
        BASELINE_ERRORS.labels(reason="failure").inc()
        api_errors_total.labels(stage="baseline").inc()
        BASELINE_FALLBACK.labels(reason="failure_exhausted").inc()
        BASELINE_LATENCY.observe(time.time() - start)
        record_slo("baseline", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "baseline", "error": str(e)}), 500


@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/metrics': make_wsgi_app()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=False, use_reloader=False)