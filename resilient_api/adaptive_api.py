# adaptive_api.py
# -----------------------------------------------------------------------
# ADAPTIVE API — Function-specific chaos behaviour
# Port: 5005
#
# KEY DISTINCTION from all other APIs:
#   - Fragile:   one fixed failure profile for every request
#   - Baseline:  uniform random stressor, same for every function
#   - Resilient: AI-weighted stressor + RL arm selection, but still
#                applied uniformly across all request types
#   - Adaptive:  EACH FUNCTION TYPE has its own chaos profile,
#                its own recovery strategy, and its own tolerance
#                thresholds. The profile self-adjusts per context.
#
# Three function contexts:
#   data_processing  — CPU-sensitive, tolerates latency, hates failures
#   llm_inference    — confidence-sensitive, tolerates slow, needs accuracy
#   realtime_query   — latency-sensitive, must be fast or it's worthless
# -----------------------------------------------------------------------

from flask import Flask, request, jsonify
from prometheus_client import (
    Counter, Histogram, Gauge,
    generate_latest, CONTENT_TYPE_LATEST, make_wsgi_app
)
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import random
import time
import logging
import threading
import psutil
from pythonjsonlogger import jsonlogger
from enum import Enum

# -----------------------------------------------------------------------
# Shared metrics (feeds the same stage-comparison panels as the others)
# -----------------------------------------------------------------------
from prometheus_client import Counter as _Counter
try:
    from metrics import api_requests_total, api_errors_total
except Exception:
    api_requests_total = _Counter(
        "api_requests_total", "Total requests per stage", ["stage"]
    )
    api_errors_total = _Counter(
        "api_errors_total", "Total errors per stage", ["stage"]
    )

app = Flask(__name__)

logger = logging.getLogger("adaptive_logger")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


# -----------------------------------------------------------------------
# Adaptive-specific Prometheus metrics
# All labelled by `function_type` so Grafana can split per context
# -----------------------------------------------------------------------
ADAPTIVE_REQUESTS = Counter(
    "adaptive_requests_total",
    "Total requests per function type",
    ["function_type"]
)
ADAPTIVE_ERRORS = Counter(
    "adaptive_errors_total",
    "Total errors per function type",
    ["function_type", "reason"]
)
ADAPTIVE_LATENCY = Histogram(
    "adaptive_latency_seconds",
    "End-to-end latency per function type",
    ["function_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
)
ADAPTIVE_STRESSOR = Counter(
    "adaptive_stressor_total",
    "Stressor drawn per function type",
    ["function_type", "stressor"]
)
ADAPTIVE_RECOVERY = Counter(
    "adaptive_recovery_total",
    "Recovery strategy used per function type",
    ["function_type", "strategy"]
)
ADAPTIVE_SLO_BREACH = Counter(
    "adaptive_slo_breach_total",
    "Requests that breached the function SLO",
    ["function_type", "slo_type"]
)
ADAPTIVE_PROFILE_WEIGHT = Gauge(
    "adaptive_profile_weight",
    "Current chaos weight for a stressor in a function context",
    ["function_type", "stressor"]
)
ADAPTIVE_SUCCESS_RATE = Gauge(
    "adaptive_success_rate",
    "Rolling success rate per function type (last 100 requests)",
    ["function_type"]
)
ADAPTIVE_CPU_SHARE = Gauge("adaptive_cpu_share", "Adaptive API CPU share")
ADAPTIVE_MEMORY_SHARE = Gauge("adaptive_memory_share", "Adaptive API memory share")

# Update CPU/memory in background
def _update_resource_metrics():
    proc = psutil.Process()
    while True:
        try:
            cpu = proc.cpu_percent(interval=1) / (psutil.cpu_count() or 1)
            mem = proc.memory_percent()
            ADAPTIVE_CPU_SHARE.set(cpu)
            ADAPTIVE_MEMORY_SHARE.set(mem)
        except Exception:
            pass

threading.Thread(target=_update_resource_metrics, daemon=True).start()

def _drift_weights_back():
    """Slowly drift adapted weights back toward originals — creates oscillation."""
    while True:
        time.sleep(30)
        with _state_lock:
            for ft, s in _state.items():
                if not s["adapted"]:
                    continue
                original = FUNCTION_CONTEXTS[ft]["stressor_weights"]
                drifted  = False
                for stressor in s["weights"]:
                    orig  = original[stressor]
                    curr  = s["weights"][stressor]
                    # Move 20% of the way back toward original
                    s["weights"][stressor] = curr + 0.20 * (orig - curr)
                    if abs(s["weights"][stressor] - orig) < 0.01:
                        s["weights"][stressor] = orig
                    else:
                        drifted = True
                # Normalise
                total = sum(s["weights"].values())
                for k in s["weights"]:
                    s["weights"][k] /= total
                # If fully drifted back, mark as un-adapted
                if not drifted:
                    s["adapted"] = False
                # Update Prometheus
                for stressor, weight in s["weights"].items():
                    ADAPTIVE_PROFILE_WEIGHT.labels(
                        function_type=ft, stressor=stressor
                    ).set(weight)

threading.Thread(target=_drift_weights_back, daemon=True).start()


# -----------------------------------------------------------------------
# Function context definitions
# Each context has:
#   slo_latency_ms   — max acceptable latency before SLO breach
#   slo_must_succeed — whether a failure always counts as SLO breach
#   stressor_weights — initial chaos injection probabilities
#   recovery_order   — ordered list of recovery strategies to try
#   tolerance        — how many consecutive failures before adapting
# -----------------------------------------------------------------------
FUNCTION_CONTEXTS = {
    "data_processing": {
        "slo_latency_ms":   1000,   # Stricter SL0 (was 2000)
        "slo_must_succeed": True,   # failures are never acceptable
        "stressor_weights": {
            "none":    0.2,
            "latency": 0.4,        # high latency weight — CPU jobs often run slow
            "timeout": 0.3,
            "failure": 0.10,
        },
        "recovery_order":   ["retry", "degrade"],
        "tolerance":        1,      # adapts after 1 consecutive failures
    },
    "llm_inference": {
        "slo_latency_ms":   3000,   # LLM calls can be slow — 3S
        "slo_must_succeed": False,  # a degraded answer is better than an error
        "stressor_weights": {
            "none":    0.25,
            "latency": 0.40,        # high latency — LLMs are inherently slow
            "timeout": 0.25,
            "failure": 0.10,
        },
        "recovery_order":   ["fallback_model", "cache", "degrade"],
        "tolerance":        2,      # lower tolerant — occasional failures OK
    },
    "realtime_query": {
        "slo_latency_ms":   100,    # strict 100ms SLO — latency IS the failure
        "slo_must_succeed": True,
        "stressor_weights": {
            "none":    0.2,        # heavily weighted to none — speed critical
            "latency": 0.30,        # latency stressor almost always breaches SLO
            "timeout": 0.35,
            "failure": 0.15,
        },
        "recovery_order":   ["degrade"],  # no retries for realtime queries — just degrade if it fails  
        "tolerance":        1,      # zero tolerance — adapts immediately
    },
}

# -----------------------------------------------------------------------
# Runtime state per function type
# Tracks rolling outcomes to drive profile adaptation
# -----------------------------------------------------------------------
_state = {
    ft: {
        "consecutive_failures": 0,
        "recent_outcomes":      [],   # last 100: True=success, False=failure
        "adapted":              False,
        "weights":              dict(ctx["stressor_weights"]),
    }
    for ft, ctx in FUNCTION_CONTEXTS.items()
}
_state_lock = threading.Lock()


def _record_outcome(function_type: str, success: bool):
    """Track rolling success rate and trigger profile adaptation if needed."""
    with _state_lock:
        s = _state[function_type]
        s["recent_outcomes"].append(success)
        if len(s["recent_outcomes"]) > 100:
            s["recent_outcomes"].pop(0)

        if success:
            s["consecutive_failures"] = 0
        else:
            s["consecutive_failures"] += 1

        # Update the Gauge so Grafana can see the rolling rate
        if s["recent_outcomes"]:
            rate = sum(s["recent_outcomes"]) / len(s["recent_outcomes"])
            ADAPTIVE_SUCCESS_RATE.labels(function_type=function_type).set(rate)

        # Adapt profile when consecutive failures exceed tolerance
        tolerance = FUNCTION_CONTEXTS[function_type]["tolerance"]
        if s["consecutive_failures"] >= tolerance:
            _adapt_profile(function_type, s)


def _adapt_profile(function_type: str, s: dict):
    """
    Context-aware adaptation: shift weights away from the stressor that
    is most likely causing failures, based on function context.
    Adaptation can happen multiple times, not just once.
    """
    ctx = FUNCTION_CONTEXTS[function_type]

    # Mark that adaptation has occurred (but don’t block future adaptations)
    s["adapted"] = True

    if function_type == "data_processing":
        s["weights"]["failure"] = max(0.02, s["weights"]["failure"] * 0.5)
        s["weights"]["timeout"] = max(0.02, s["weights"]["timeout"] * 0.5)
        s["weights"]["none"]   += 0.15
        logger.info(f"[{function_type}] Adapted aggressively: reduced failure/timeout weights")

    elif function_type == "llm_inference":
        s["weights"]["failure"] = max(0.02, s["weights"]["failure"] * 0.4)
        s["weights"]["latency"] += 0.10   # latency is acceptable for LLM
        s["weights"]["none"]   += 0.10
        logger.info(f"[{function_type}] Adapted aggressively: reduced failure weight, boosted latency tolerance")

    elif function_type == "realtime_query":
        s["weights"]["latency"] = max(0.01, s["weights"]["latency"] * 0.2)
        s["weights"]["timeout"] = max(0.01, s["weights"]["timeout"] * 0.2)
        s["weights"]["none"]   += 0.25
        logger.info(f"[{function_type}] Adapted aggressively: slashed latency/timeout weights")

    # Normalise weights so they sum to 1
    total = sum(s["weights"].values())
    for k in s["weights"]:
        s["weights"][k] /= total

    # Reset so adaptation triggers again after next tolerance window
    s["consecutive_failures"] = 0
    # Partially un-adapt over time — weights drift back toward original
    # This creates the oscillation visible in the profile weights panel

    # Expose adapted weights to Prometheus
    for stressor, weight in s["weights"].items():
        ADAPTIVE_PROFILE_WEIGHT.labels(
            function_type=function_type, stressor=stressor
        ).set(weight)


def _get_stressor(function_type: str) -> str:
    """Draw a stressor from the current (possibly adapted) profile."""
    with _state_lock:
        weights = _state[function_type]["weights"]
    stressors = list(weights.keys())
    probs     = list(weights.values())
    chosen    = random.choices(stressors, weights=probs)[0]
    ADAPTIVE_STRESSOR.labels(function_type=function_type, stressor=chosen).inc()
    return chosen


# -----------------------------------------------------------------------
# Per-function execution — each function type has unique behaviour
# under each stressor, reflecting real-world function characteristics
# -----------------------------------------------------------------------

def _execute_data_processing(value: float, stressor: str) -> dict:
    """
    Simulates a CPU-bound data job.
    Latency is annoying but survivable. Failure corrupts the pipeline.
    Recovery: retry up to 2x, then return partial result.
    """
    if stressor == "none":
        # Normal: simulate CPU work proportional to value size
        work_time = min(0.1 + abs(value) * 0.001, 0.5)
        time.sleep(work_time)
        return {"result": value * 3.14159, "quality": "full", "iterations": 1}

    elif stressor == "latency":
        # Slow CPU — still completes but takes longer
        delay = random.uniform(0.5, 1.8)
        time.sleep(delay)
        return {"result": value * 3.14159, "quality": "full", "iterations": 1,
                "latency_injected_ms": delay * 1000}

    elif stressor == "timeout":
        raise TimeoutError("data_processing: CPU job timed out — pipeline stall")

    elif stressor == "failure":
        raise RuntimeError("data_processing: job failed — pipeline integrity at risk")


def _execute_llm_inference(value: float, stressor: str) -> dict:
    """
    Simulates an LLM inference call.
    High latency is expected and tolerated. Low confidence triggers fallback.
    Recovery: try secondary model, then cached answer, then degrade.
    """
    if stressor == "none":
        time.sleep(random.uniform(0.3, 0.8))   # LLMs are always a bit slow
        confidence = random.uniform(0.82, 0.97)
        return {
            "answer":     f"LLM processed: {value}",
            "confidence": confidence,
            "source":     "primary_model",
            "quality":    "high" if confidence > 0.9 else "acceptable"
        }

    elif stressor == "latency":
        # Very slow inference — still valid but might miss SLO
        delay = random.uniform(1.5, 4.5)
        time.sleep(delay)
        confidence = random.uniform(0.75, 0.92)
        return {
            "answer":     f"LLM processed (slow): {value}",
            "confidence": confidence,
            "source":     "primary_model",
            "quality":    "slow_but_valid",
            "latency_injected_ms": delay * 1000
        }

    elif stressor == "timeout":
        # Model timed out — trigger fallback_model recovery
        raise TimeoutError("llm_inference: primary model timeout — triggering fallback")

    elif stressor == "failure":
        # Model crash — confidence is undefined
        raise RuntimeError("llm_inference: model inference failed — confidence unknown")


def _execute_realtime_query(value: float, stressor: str) -> dict:
    """
    Simulates a realtime lookup (e.g. feature store, cache hit, live DB).
    Anything over 200ms is a SLO breach. Latency IS the failure here.
    Recovery: only cache or degrade — no retry (too slow).
    """
    if stressor == "none":
        time.sleep(random.uniform(0.01, 0.08))   # sub-100ms baseline
        return {
            "result":      value * 2,
            "source":      "live",
            "latency_ms":  random.uniform(10, 80),
            "freshness":   "realtime"
        }

    elif stressor == "latency":
        # Any injected latency almost certainly breaches the 200ms SLO
        delay = random.uniform(0.25, 1.2)
        time.sleep(delay)
        return {
            "result":      value * 2,
            "source":      "live_but_slow",
            "latency_ms":  delay * 1000,
            "freshness":   "stale_slo_breach"
        }

    elif stressor == "timeout":
        raise TimeoutError("realtime_query: upstream timeout — SLO breached")

    elif stressor == "failure":
        raise RuntimeError("realtime_query: data source unavailable")


# Dispatch table — maps function_type to its executor
_EXECUTORS = {
    "data_processing": _execute_data_processing,
    "llm_inference":   _execute_llm_inference,
    "realtime_query":  _execute_realtime_query,
}

# Recovery strategies — each function type orders these differently
def _recover(function_type: str, value: float, error: Exception, strategy: str) -> dict:
    """Attempt a recovery strategy. Returns result dict or raises."""
    ADAPTIVE_RECOVERY.labels(function_type=function_type, strategy=strategy).inc()

    if strategy == "retry":
        # Retry succeeds only 70% of the time
        if random.random() < 0.3:
            raise RuntimeError("Retry failed")
        executor = _EXECUTORS[function_type]
        return executor(value, "none")

    elif strategy == "fallback_model":
        # Fallback sometimes produces very low confidence
        confidence = random.uniform(0.4, 0.7)
        if confidence < 0.5:
            raise RuntimeError("Fallback model produced unusable output")
        return {
            "answer":     f"[FALLBACK MODEL] processed: {value}",
            "confidence": confidence,
            "source":     "secondary_model",
            "quality":    "degraded"
        }

    elif strategy == "cache":
        # Cache occasionally fails to return data
        if random.random() < 0.2:
            raise RuntimeError("Cache miss")
        return {
            "result":    value * 2,
            "source":    "cache",
            "freshness": "stale",
            "quality":   "cached"
        }

    elif strategy == "degrade":
        # Last resort — return a degraded but valid response
        return {
            "result":  None,
            "source":  "degraded",
            "quality": "minimal",
            "message": f"Service degraded for {function_type} — partial response only"
        }

    raise ValueError(f"Unknown recovery strategy: {strategy}")


# -----------------------------------------------------------------------
# SLO checker — per function type, per metric
# -----------------------------------------------------------------------
def _check_slo(function_type: str, elapsed_ms: float, succeeded: bool):
    ctx = FUNCTION_CONTEXTS[function_type]

    if elapsed_ms > ctx["slo_latency_ms"]:
        ADAPTIVE_SLO_BREACH.labels(
            function_type=function_type, slo_type="latency"
        ).inc()
        logger.warning(f"SLO breach [{function_type}]: latency {elapsed_ms:.0f}ms "
                       f"> {ctx['slo_latency_ms']}ms")

    if ctx["slo_must_succeed"] and not succeeded:
        ADAPTIVE_SLO_BREACH.labels(
            function_type=function_type, slo_type="availability"
        ).inc()


# -----------------------------------------------------------------------
# Route
# -----------------------------------------------------------------------
@app.route("/adaptive-api/process", methods=["POST"])
def adaptive_process():
    data          = request.get_json(force=True) or {}
    value         = data.get("value", 1.0)
    function_type = data.get("function_type", "data_processing")

    if function_type not in FUNCTION_CONTEXTS:
        return jsonify({
            "error": f"Unknown function_type '{function_type}'. "
                     f"Must be one of: {list(FUNCTION_CONTEXTS.keys())}"
        }), 400

    # Count against both adaptive-specific and shared stage metrics
    ADAPTIVE_REQUESTS.labels(function_type=function_type).inc()
    api_requests_total.labels(stage="adaptive").inc()

    start   = time.time()
    ctx     = FUNCTION_CONTEXTS[function_type]
    executor = _EXECUTORS[function_type]

    # Draw a context-specific stressor
    stressor = _get_stressor(function_type)

    try:
        result    = executor(value, stressor)
        elapsed   = (time.time() - start) * 1000
        succeeded = True

        ADAPTIVE_LATENCY.labels(function_type=function_type).observe(elapsed / 1000)
        slo_ok = elapsed <= ctx["slo_latency_ms"]
        _check_slo(function_type, elapsed, succeeded=True)
        # Count as success only if SLO was met — latency breaches still degrade rate
        _record_outcome(function_type, success=slo_ok)

        logger.info("Adaptive success", extra={
            "function_type": function_type,
            "stressor":      stressor,
            "elapsed_ms":    elapsed,
        })

        return jsonify({
            "stage":         "adaptive",
            "function_type": function_type,
            "stressor":      stressor,
            "result":        result,
            "elapsed_ms":    round(elapsed, 2),
            "slo_limit_ms":  ctx["slo_latency_ms"],
            "slo_ok":        elapsed <= ctx["slo_latency_ms"],
            "adapted":       _state[function_type]["adapted"],
        }), 200

    except Exception as primary_exc:
        # Primary execution failed — work through the recovery order
        ADAPTIVE_ERRORS.labels(
            function_type=function_type,
            reason=type(primary_exc).__name__
        ).inc()
        api_errors_total.labels(stage="adaptive").inc()

        recovery_result = None
        recovery_used   = None

        for strategy in ctx["recovery_order"]:
            try:
                recovery_result = _recover(function_type, value, primary_exc, strategy)
                recovery_used   = strategy
                break
            except Exception:
                continue

        elapsed   = (time.time() - start) * 1000
        succeeded = recovery_result is not None

        ADAPTIVE_LATENCY.labels(function_type=function_type).observe(elapsed / 1000)
        _check_slo(function_type, elapsed, succeeded=succeeded)
        # Recovery = degraded outcome — always count as failure for rolling rate
        # This ensures the rolling rate drops when chaos fires, making
        # the adaptation trigger and the Grafana panel visibly non-flat
        _record_outcome(function_type, success=False)

        if succeeded:
            logger.warning("Adaptive recovered", extra={
                "function_type":   function_type,
                "stressor":        stressor,
                "primary_error":   str(primary_exc),
                "recovery_used":   recovery_used,
                "elapsed_ms":      elapsed,
            })
            return jsonify({
                "stage":           "adaptive",
                "function_type":   function_type,
                "stressor":        stressor,
                "result":          recovery_result,
                "elapsed_ms":      round(elapsed, 2),
                "slo_ok":          elapsed <= ctx["slo_latency_ms"],
                "recovered_via":   recovery_used,
                "primary_error":   str(primary_exc),
                "adapted":         _state[function_type]["adapted"],
            }), 200
        else:
            logger.error("Adaptive all recoveries failed", extra={
                "function_type": function_type,
                "stressor":      stressor,
                "error":         str(primary_exc),
            })
            return jsonify({
                "stage":         "adaptive",
                "function_type": function_type,
                "stressor":      stressor,
                "error":         str(primary_exc),
                "elapsed_ms":    round(elapsed, 2),
                "outcome":       "all_recoveries_failed",
                "adapted":       _state[function_type]["adapted"],
            }), 500


@app.route("/adaptive-api/profile", methods=["GET"])
def get_profiles():
    """Expose current (possibly adapted) chaos weights for all function types."""
    with _state_lock:
        profiles = {
            ft: {
                "current_weights":      dict(s["weights"]),
                "original_weights":     dict(FUNCTION_CONTEXTS[ft]["stressor_weights"]),
                "adapted":              s["adapted"],
                "consecutive_failures": s["consecutive_failures"],
                "recent_success_rate":  (
                    sum(s["recent_outcomes"]) / len(s["recent_outcomes"])
                    if s["recent_outcomes"] else None
                ),
                "slo_latency_ms":       FUNCTION_CONTEXTS[ft]["slo_latency_ms"],
                "recovery_order":       FUNCTION_CONTEXTS[ft]["recovery_order"],
            }
            for ft, s in _state.items()
        }
    return jsonify(profiles), 200


@app.route("/adaptive-api/reset", methods=["POST"])
def reset_profiles():
    """Reset all function profiles back to their original weights."""
    with _state_lock:
        for ft, ctx in FUNCTION_CONTEXTS.items():
            _state[ft]["weights"]              = dict(ctx["stressor_weights"])
            _state[ft]["consecutive_failures"] = 0
            _state[ft]["adapted"]              = False
            _state[ft]["recent_outcomes"]      = []
            for stressor, weight in ctx["stressor_weights"].items():
                ADAPTIVE_PROFILE_WEIGHT.labels(
                    function_type=ft, stressor=stressor
                ).set(weight)
    return jsonify({"status": "profiles reset to defaults"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# Initialise the weight gauges on startup so Grafana has baseline values
for _ft, _ctx in FUNCTION_CONTEXTS.items():
    for _s, _w in _ctx["stressor_weights"].items():
        ADAPTIVE_PROFILE_WEIGHT.labels(function_type=_ft, stressor=_s).set(_w)

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=False, use_reloader=False)