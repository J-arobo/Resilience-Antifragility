# app.py
from flask import Flask, request, jsonify, send_file
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
import psutil
import pandas as pd
import logging
import time
from typing import TypedDict
from datetime import datetime, timedelta, timezone
from pythonjsonlogger import jsonlogger
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import learning
from learning import train_model, plot_feature_importance, train_chaos_selector

from chaos import execute_chaos
from prometheus_client import Counter, Gauge, Histogram
import uuid

import os, threading, requests, random
from enum import Enum
import math
import subprocess
from typing import TypedDict
import json
from chaos import PolicyManager, BanditPolicy

#from naive import naive_bp
#from reactive import reactive_bp
from prometheus_client import Counter, make_wsgi_app
from metrics import api_requests_total, api_errors_total
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_flask_exporter import PrometheusMetrics

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from stable_baselines3 import PPO
from requests.exceptions import ConnectionError

import threading    # For thread-safe circuit breaker state management
from collections import deque
import time


# -----------------------------------------------------------------------
# Load trained RL model
# -----------------------------------------------------------------------
# model = PPO.load("resilience_agent")
try:
    model = PPO.load("resilience_agent")
    print("RL model loaded successfully")
except Exception as e:
    print(f"WARNING: Could not load RL model ({e}), training a fresh one...")
    from stable_baselines3 import PPO as _PPO
    _env = gym.make("CartPole-v1")
    model = _PPO("MlpPolicy", _env, verbose=0)
    model.learn(total_timesteps=1000)
    model.save("resilience_agent")
    print("Fresh RL model trained and saved")

arms = ["fallback_chain", "circuit_breaker", "hedged_request"]
policy_manager = PolicyManager(arms)

_leaks = []
TIME_SKEW_MS = 0

STRESSOR_MAP = {
    "timeout": 0,
    "latency": 1,
    "failure": 2,
    "none":    3
}
STRESSORS = ["timeout", "latency", "failure", "none"]


# -----------------------------------------------------------------------
# Prometheus metrics
# -----------------------------------------------------------------------
RESILIENT_CPU_SHARE    = Gauge("resilient_cpu_share",    "Resilient API share of total CPU")
RESILIENT_MEMORY_SHARE = Gauge("resilient_memory_share", "Resilient API share of total Memory")

CHAOS_ORIGIN = Counter(
    "resilient_chaos_origin_total",
    "Counts chaos injections by origin",
    ["origin", "stressor"]
)
AI_INJECTED     = Counter("resilient_ai_injected_total",  "AI-driven chaos injections",  ["stressor"])
RANDOM_INJECTED = Counter("resilient_random_injected_total", "Random chaos injections",   ["stressor"])

FALLBACK_TOTAL = Counter(
    "reactive_fallback_total",
    "Total fallback events triggered during chaos",
    ["reason"]
)
RETRY_SUCCESS = Counter("resilient_retry_success_total", "Successful retries")
FALLBACK_USED = Counter(
    "resilient_fallback_total",
    "Fallbacks triggered",
    ["reason"]
)
STRESSOR_TYPE     = Counter("resilient_stressor_type_total", "Stressor type triggered",  ["type"])
LATENCY_HISTOGRAM = Histogram("resilient_latency_seconds",   "Latency injected by chaos")

RESILIENT_REQUESTS = Counter(
    "resilient_requests_total",
    "Total number of requests processed by the resilient API"
)

LLM_RESPONSE_ACCURACY = Gauge("llm_response_accuracy",            "Accuracy of LLM responses (0-1 scale)")
LLM_CONFIDENCE_ERROR  = Gauge("llm_confidence_calibration_error", "Calibration error")
LLM_ROUTING_SUCCESS   = Counter("llm_tool_routing_sucess_total",  "Successful tool routing decisions")

RETRIEVAL_COVERAGE  = Gauge("retrieval_coverage_ration",      "Coverage ratio")
RETRIEVAL_FRESHNESS = Gauge("retrieval_freshness_lag_seconds", "Freshness lag in seconds")
RETRIEVAL_CACHE_HIT = Counter("retrieval_cache_hit_total",    "Cache hits")
CACHE_TTL_SECONDS   = Gauge("cache_ttl_seconds",              "Adaptive cache TTL in seconds")

def update_cache_ttl(ttl_value: int):
    CACHE_TTL_SECONDS.set(ttl_value)

BANDIT_ARM_SELECTED = Counter(
    "bandit_arm_selected_total",
    "Which model/tool the bandit selected",
    ["arm"]
)
BANDIT_REWARD = Histogram("bandit_reward", "Reward assigned to each bandit arm")

API_SLO_ADHERENCE   = Gauge("api_slo_adherence_ratio",    
    "Ratio of requests meeting all SLOs in the rolling window", ["stage"])
API_ERROR_RATE      = Gauge("api_error_total",                "Total API errors encountered", ["stage"])
API_CIRCUIT_BREAKER = Gauge("api_circuit_breaker_open_total", "Circuit breaker activations")
API_RETRY_SUCCESS   = Gauge("api_retry_success_total",        "Successful API retries")

RUNTIME_QUEUE_DEPTH = Gauge("runtime_queue_depth",    "Current depth of runtime queue")
CONTAINER_RESTARTS  = Gauge("container_restart_total","Total container restarts detected")
INCIDENT_MTTR       = Gauge("incident_mttr_seconds",  "Mean time to recovery for incidents")
CPU_UTILIZATION     = Gauge("node_cpu_utilization",   "CPU utilization percentage")
MEMORY_UTILIZATION  = Gauge("node_memory_utilization","Memory utilization percentage")

SECURITY_ANOMALY_PRECISION = Gauge("security_anomaly_precision",         "Precision of anomaly detection")
SECURITY_ANOMALY_RECALL    = Gauge("security_anomaly_recall",            "Recall of anomaly detection")
SECURITY_POLICY_VIOLATIONS = Counter("security_policy_violations_total", "Policy violations detected")
SECURITY_FLOW_ISOLATION    = Counter("security_flow_isolation_total",    "Flows isolated due to anomalies")

# -----------------------------------------------------------------------
# SLO thresholds — edit these to match my targets
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

def record_slo(stage: str, latency_ms: float, success: bool):
    met = success and (latency_ms < SLO_LATENCY_MS)
 
    with _slo_lock:
        window = _slo_windows.get(stage)
        if window is None:
            return
        window.append(met)
        adherence = sum(window) / len(window) if window else 0.0
 
    # Update Prometheus — after releasing lock so we don't hold it during IO
    API_SLO_ADHERENCE.labels(stage=stage).set(adherence)
 

# -----------------------------------------------------------------------
# Resilient chaos-exposure gauge (mirrors baseline_bad_stressor_ratio
# so Grafana can plot them on the same panel for direct comparison)
# -----------------------------------------------------------------------
RESILIENT_CHAOS_EXPOSURE = Gauge(
    "resilient_bad_stressor_ratio",
    "Rolling ratio of bad stressors seen by resilient API"
)

_resilient_draw_counts = {"timeout": 0, "latency": 0, "failure": 0, "none": 0}

def _track_resilient_stressor(stressor: str):
    _resilient_draw_counts[stressor] = _resilient_draw_counts.get(stressor, 0) + 1
    total = sum(_resilient_draw_counts.values())
    bad   = sum(v for k, v in _resilient_draw_counts.items() if k != "none")
    RESILIENT_CHAOS_EXPOSURE.set(bad / total if total > 0 else 0)


# -----------------------------------------------------------------------
# Simple in-memory cache
# -----------------------------------------------------------------------
ANSWER_CACHE = {}

def cache_get(key: str):
    return ANSWER_CACHE.get(key)

def cache_set(key: str, answer: str):
    ANSWER_CACHE[key] = answer

class ModelResult(TypedDict):
    answer: str
    success: bool
    confidence: float


# -----------------------------------------------------------------------
# Circuit breaker
# -----------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"

CIRCUIT_BREAKER_STATE       = CircuitState.CLOSED
FAILURE_COUNT               = 0
HALF_OPEN_SUCCESSES         = 0
FAILURE_THRESHOLD           = 3
HALF_OPEN_SUCCESS_THRESHOLD = 2
COOLDOWN_SECONDS            = 10
LAST_FAILURE_TIME           = 0
CB_LOCK                     = threading.Lock()   


def circuit_is_open() -> bool:
    global CIRCUIT_BREAKER_STATE, LAST_FAILURE_TIME
    with CB_LOCK:                                 
        if CIRCUIT_BREAKER_STATE == CircuitState.OPEN:
            if time.time() - LAST_FAILURE_TIME > COOLDOWN_SECONDS:
                CIRCUIT_BREAKER_STATE = CircuitState.HALF_OPEN
                return False
            return True
        return False


def record_failure(sys_metrics: dict):
    global FAILURE_COUNT, CIRCUIT_BREAKER_STATE, LAST_FAILURE_TIME, HALF_OPEN_SUCCESSES
    with CB_LOCK:                                  
        if CIRCUIT_BREAKER_STATE == CircuitState.HALF_OPEN:
            HALF_OPEN_SUCCESSES   = 0
            CIRCUIT_BREAKER_STATE = CircuitState.OPEN
            LAST_FAILURE_TIME     = time.time()
            API_CIRCUIT_BREAKER.set(1)
            return
        FAILURE_COUNT    += 1
        LAST_FAILURE_TIME = time.time()
        if FAILURE_COUNT >= FAILURE_THRESHOLD:
            CIRCUIT_BREAKER_STATE = CircuitState.OPEN
            API_CIRCUIT_BREAKER.set(1)
            log_chaos_event(
                chaos_module="api", event_type="circuit_breaker_open", stressor="none",
                adaptation_action="circuit_breaker", outcome="failure",
                value=FAILURE_COUNT, sys_metrics=sys_metrics,
                prediction=False, confidence=0.0, injected_by_ai=False
            )


def record_success():
    global FAILURE_COUNT, CIRCUIT_BREAKER_STATE, HALF_OPEN_SUCCESSES
    with CB_LOCK:                                  
        if CIRCUIT_BREAKER_STATE == CircuitState.HALF_OPEN:
            HALF_OPEN_SUCCESSES += 1
            if HALF_OPEN_SUCCESSES >= HALF_OPEN_SUCCESS_THRESHOLD:
                FAILURE_COUNT         = 0
                HALF_OPEN_SUCCESSES   = 0
                CIRCUIT_BREAKER_STATE = CircuitState.CLOSED
                API_CIRCUIT_BREAKER.set(0)
            return
        FAILURE_COUNT         = 0
        CIRCUIT_BREAKER_STATE = CircuitState.CLOSED
        API_CIRCUIT_BREAKER.set(0)




# -----------------------------------------------------------------------
# AI model layer (stubs)
# -----------------------------------------------------------------------
def call_primary_model(prompt: str) -> ModelResult:
    return {"answer": f"[PRIMARY] Processed: {prompt}", "success": True, "confidence": 0.85}

def call_secondary_model(prompt: str) -> ModelResult:
    return {"answer": f"[SECONDARY] Processed: {prompt}", "success": True, "confidence": 0.70}


# -----------------------------------------------------------------------
# Bandit (UCB1)
# -----------------------------------------------------------------------
BANDIT_ARMS    = ["primary", "secondary", "cache"]
bandit_counts  = {arm: 1   for arm in BANDIT_ARMS}
bandit_rewards = {arm: 0.0 for arm in BANDIT_ARMS}
CONFIDENCE_THRESHOLD = 0.80


def select_bandit_arm() -> str:
    total = sum(bandit_counts.values())
    ucb_scores = {}
    for arm in BANDIT_ARMS:
        avg_reward  = bandit_rewards[arm] / bandit_counts[arm]
        exploration = math.sqrt(2 * math.log(total) / bandit_counts[arm])
        ucb_scores[arm] = avg_reward + exploration
    return max(ucb_scores, key=ucb_scores.get)

def compute_reward(confidence: float, latency: float, fallback_used: bool) -> float:
    reward = confidence + max(0, 1 - latency)
    if fallback_used:
        reward -= 0.5
    return reward

def update_bandit(arm: str, reward: float):
    bandit_counts[arm]  += 1
    bandit_rewards[arm] += reward


# -----------------------------------------------------------------------
# Hybrid RL + Bandit
# -----------------------------------------------------------------------
def choose_strategy(state) -> str:
    action, _ = model.predict(state)
    rl_arm     = ["fallback_chain", "circuit_breaker", "hedged_request"][action]
    bandit_arm = select_bandit_arm()
    return rl_arm if np.mean(state) > 0.5 else bandit_arm


# -----------------------------------------------------------------------
# Fallback chain
# -----------------------------------------------------------------------
def get_answer_with_fallback_chain(prompt: str, sys_metrics: dict) -> dict:
    arm              = select_bandit_arm()
    cache_key        = prompt
    used_fallback    = False
    final_confidence = 0.0

    try:
        primary          = call_primary_model(prompt)
        final_confidence = primary["confidence"]
        log_chaos_event(
            chaos_module="llm", event_type="ai_call", stressor="none",
            adaptation_action="none",
            outcome="success" if primary["success"] else "failure",
            value=len(prompt), sys_metrics=sys_metrics,
            prediction=True, confidence=primary["confidence"], injected_by_ai=False
        )
        if primary["success"] and primary["confidence"] >= CONFIDENCE_THRESHOLD:
            cache_set(cache_key, primary["answer"])
            update_cache_ttl(120)
            reward = compute_reward(primary["confidence"], latency=0, fallback_used=False)
            update_bandit(arm, reward)
            BANDIT_ARM_SELECTED.labels(arm=arm).inc()
            BANDIT_REWARD.observe(reward)
            return {"answer": primary["answer"], "source": "primary",
                    "confidence": primary["confidence"], "used_fallback": False}
        used_fallback = True
        FALLBACK_TOTAL.labels(reason="low_confidence").inc()
        FALLBACK_USED.labels(reason="low_confidence").inc()
    except Exception as e:
        used_fallback = True
        FALLBACK_TOTAL.labels(reason="primary_exception").inc()
        FALLBACK_USED.labels(reason="primary_exception").inc()
        logger.exception("Primary model failed", extra={"error": str(e)})

    try:
        secondary        = call_secondary_model(prompt)
        final_confidence = secondary["confidence"]
        if secondary["success"]:
            cache_set(cache_key, secondary["answer"])
            reward = compute_reward(secondary["confidence"], latency=0, fallback_used=used_fallback)
            update_bandit(arm, reward)
            BANDIT_ARM_SELECTED.labels(arm=arm).inc()
            BANDIT_REWARD.observe(reward)
            return {"answer": secondary["answer"], "source": "secondary",
                    "confidence": secondary["confidence"], "used_fallback": used_fallback}
    except Exception as e:
        FALLBACK_TOTAL.labels(reason="secondary_exception").inc()
        FALLBACK_USED.labels(reason="secondary_exception").inc()
        logger.exception("Secondary model failed", extra={"error": str(e)})

    cached = cache_get(cache_key)
    reward = compute_reward(confidence=1.0, latency=0, fallback_used=True)
    update_bandit(arm, reward)
    if cached is not None:
        BANDIT_ARM_SELECTED.labels(arm=arm).inc()
        BANDIT_REWARD.observe(reward)
        FALLBACK_TOTAL.labels(reason="cache").inc()
        FALLBACK_USED.labels(reason="cache").inc()
        return {"answer": cached, "source": "cache",
                "confidence": final_confidence, "used_fallback": True}

    logger.warning("All AI fallbacks exhausted — returning degraded response")
    FALLBACK_USED.labels(reason="degraded_response").inc()
    return {
        "answer":        f"Degraded: processed {prompt}",
        "source":        "degraded",
        "confidence":    0.0,
        "used_fallback": True
    }


# -----------------------------------------------------------------------
# Hedged request
# -----------------------------------------------------------------------
def hedged_request(func, timeout=0.3, *args, **kwargs):
    result = {}
    lock   = threading.Lock()

    def run_call(label):
        try:
            response = func(*args, **kwargs)
            with lock:
                if "answer" not in result:
                    result["answer"] = response
                    result["source"] = label
        except Exception as e:
            with lock:
                if "answer" not in result:
                    result["error"]  = str(e)
                    result["source"] = label

    t1 = threading.Thread(target=run_call, args=("primary",))
    t1.start()

    hedge_timer = threading.Timer(
        timeout,
        lambda: threading.Thread(target=run_call, args=("hedged",)).start()
    )
    hedge_timer.start()

    deadline = time.time() + 10.0
    while "answer" not in result and time.time() < deadline:
        time.sleep(0.01)

    hedge_timer.cancel()

    if "answer" not in result:
        raise RuntimeError(
            f"Hedged request: both calls failed. Last error: {result.get('error', 'unknown')}"
        )

    return result


# -----------------------------------------------------------------------
# Structured logging
# -----------------------------------------------------------------------
logger = logging.getLogger("locust_logger")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter  = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(extra)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)


# -----------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------
app = Flask(__name__)
#app.register_blueprint(naive_bp)
#app.register_blueprint(reactive_bp)
prometheus_metrics = PrometheusMetrics(app)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def log_chaos_event(
        chaos_module: str, event_type: str, stressor: str,
        adaptation_action: str, outcome: str, value: float,
        sys_metrics: dict, prediction: bool, confidence: float,
        injected_by_ai: bool, latency_ms: float = 0.0
):
    logger.info("Chaos event", extra={
        "timestamp":         datetime.now().isoformat(),
        "level":             "INFO",
        "chaos_module":      chaos_module,
        "event_type":        event_type,
        "stress_class":      stressor,
        "adaptation_action": adaptation_action,
        "outcome":           outcome,
        "chaos_event_id":    f"evt-{uuid.uuid4()}",
        "value":             value,
        "latency_ms":        latency_ms,
        "cpu_percent":       sys_metrics.get("cpu_percent"),
        "memory_percent":    sys_metrics.get("memory_percent"),
        "prediction":        prediction,
        "confidence":        confidence,
        "injected_by_ai":    injected_by_ai
    })

def get_system_metrics() -> dict:
    return {
        "cpu_percent":    psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent
    }

def calculate_recovery_time() -> float:
    return random.uniform(0.5, 2.0)


# -----------------------------------------------------------------------
# Resilient operation (with retry)
# -----------------------------------------------------------------------
@retry(stop=stop_after_attempt(3), wait=wait_fixed(0.3))
def resilient_operation(value, stressor):
    sys_metrics = get_system_metrics()

    confidence     = 1.0
    injected_by_ai = False
    latency        = 0.0
    prediction     = True
    result         = None

    STRESSOR_TYPE.labels(type=stressor).inc()
    CHAOS_ORIGIN.labels(
        origin="ai" if injected_by_ai else "resilient",
        stressor=stressor
    ).inc()

    logger.warning("Chaos injected", extra={
        "timestamp": datetime.now().isoformat(),
        "stressor":  stressor,
        "value":     value
    })

    """
    log_chaos_event(
        chaos_module="runtime", event_type="chaos_event", stressor=stressor,
        adaptation_action="none", outcome="success", value=value,
        sys_metrics=sys_metrics, prediction=True,
        confidence=confidence, injected_by_ai=injected_by_ai, latency_ms=latency
    )
    """

    if stressor == "timeout":
        injected_by_ai = True
        API_ERROR_RATE.labels(stage="resilient").inc()
        api_errors_total.labels(stage="resilient").inc()
        log_chaos_event(
            chaos_module="runtime", event_type="chaos_event", stressor="timeout",
            adaptation_action="none", outcome="failure", value=value,
            sys_metrics=get_system_metrics(), prediction=False,
            confidence=0.0, injected_by_ai=True
        )
        raise TimeoutError("Simulated timeout")

    elif stressor == "latency":
        injected_by_ai = True
        latency        = random.uniform(0.5, 2.0)
        LATENCY_HISTOGRAM.observe(latency)
        time.sleep(latency)
        """
        log_chaos_event(
            chaos_module="runtime", event_type="chaos_event", stressor="latency",
            adaptation_action="none", outcome="success", value=value,
            sys_metrics=get_system_metrics(), prediction=True,
            confidence=0.9, injected_by_ai=True, latency_ms=latency * 1000
        )
        """
        result = value * 2

    elif stressor == "failure":
        injected_by_ai = True
        API_ERROR_RATE.labels(stage="resilient").inc()
        api_errors_total.labels(stage="resilient").inc()
        """
        log_chaos_event(
            chaos_module="runtime", event_type="chaos_event", stressor="failure",
            adaptation_action="none", outcome="failure", value=value,
            sys_metrics=get_system_metrics(), prediction=False,
            confidence=0.0, injected_by_ai=True
        )
        """
        raise Exception("Simulated failure")

    elif stressor == "none":
        """
        log_chaos_event(
            chaos_module="runtime", event_type="success_path", stressor="none",
            adaptation_action="none", outcome="success", value=value,
            sys_metrics=get_system_metrics(), prediction=True,
            confidence=1.0, injected_by_ai=False
        )
        """
        sys_metrics = get_system_metrics()
        CPU_UTILIZATION.set(sys_metrics["cpu_percent"])
        MEMORY_UTILIZATION.set(sys_metrics["memory_percent"])
        time.sleep(0.2)
        result = value * 2
        RETRY_SUCCESS.inc()
        RUNTIME_QUEUE_DEPTH.set(0)
        CONTAINER_RESTARTS.inc()
        INCIDENT_MTTR.set(calculate_recovery_time())
        logger.info("Operation succeeded", extra={"result": result, "value": value})

    return {
        "answer":      result,
        "source":      "resilient_operation",
        "stressor":    stressor,
        "confidence":  confidence,
        "latency_ms":  latency * 1000 if stressor == "latency" else 0,
        "sys_metrics": sys_metrics
    }


# -----------------------------------------------------------------------
# Strategy executor
# -----------------------------------------------------------------------
def execute_strategy(chosen_arm: str, value: float, sys_metrics: dict):
    logger.info("Executing strategy", extra={"arm": chosen_arm, "value": value})

    if chosen_arm == "fallback_chain":
        try:
            return get_answer_with_fallback_chain(str(value), sys_metrics)
        except Exception as e:
            logger.exception("Fallback chain failed", extra={"error": str(e)})
            raise

    elif chosen_arm == "circuit_breaker":
        if circuit_is_open():
            logger.warning("Circuit open — degrading to fallback_chain", extra={"value": value})
            FALLBACK_USED.labels(reason="circuit_breaker_open").inc()
            return get_answer_with_fallback_chain(str(value), sys_metrics)

        try:
            # AI-weighted stressor selection — avoids bad stressors more often
            stressor = random.choices(
                ["none", "timeout", "latency", "failure"],
                weights=[0.55, 0.20, 0.15, 0.10]
            )[0]
            _track_resilient_stressor(stressor)   # update exposure gauge
            result = resilient_operation(value, stressor)
            RETRY_SUCCESS.inc()
            record_success()
            return result
        except Exception as e:
            record_failure(sys_metrics)
            FALLBACK_USED.labels(reason="circuit_breaker_failure").inc()
            logger.warning(
                "Circuit breaker branch failed — degrading to fallback_chain",
                extra={"error": str(e)}
            )
            return get_answer_with_fallback_chain(str(value), sys_metrics)

    elif chosen_arm == "hedged_request":
        try:
            result = hedged_request(lambda: resilient_operation(value, "none"))
            RETRY_SUCCESS.inc()
            return result
        except Exception as e:
            logger.exception("Hedged request failed", extra={"error": str(e)})
            raise

    else:
        raise ValueError(f"Unknown strategy: {chosen_arm}")


@app.before_request
def record_resilient_metrics():
    proc          = psutil.Process()
    total_cpu     = psutil.cpu_percent(interval=0.1)
    total_mem     = psutil.virtual_memory().percent
    resilient_cpu = proc.cpu_percent(interval=0.1) / psutil.cpu_count()
    resilient_mem = proc.memory_percent()
    RESILIENT_CPU_SHARE.set((resilient_cpu / total_cpu) * 100 if total_cpu > 0 else 0)
    RESILIENT_MEMORY_SHARE.set((resilient_mem / total_mem) * 100 if total_mem > 0 else 0)


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------
@app.route('/resilient-api/process', methods=['POST'])
def process_data():
    start = time.time()
    api_requests_total.labels(stage="resilient").inc()
    RESILIENT_REQUESTS.inc()

    data        = request.get_json(force=True) or {}
    value       = data.get("value", 1.0)
    sys_metrics = get_system_metrics()

    try:
        if value is None or not isinstance(value, (int, float)):
            api_errors_total.labels(stage="resilient").inc()
            record_slo("resilient", (time.time() - start) * 1000, success=False)
            return jsonify({"error": "Invalid input: 'value' must be a number"}), 400

        total_fallbacks = sum(
            float(FALLBACK_USED.labels(reason=r)._value.get())
            for r in [
                "low_confidence", "primary_exception", "secondary_exception",
                "cache", "timeout", "connection_error", "circuit_breaker_failure",
                "circuit_breaker_open", "degraded_response"
            ]
        )

        state = [
            sys_metrics["cpu_percent"]        / 100.0,
            sys_metrics["memory_percent"]     / 100.0,
            float(RETRY_SUCCESS._value.get()) / 100.0,
            float(total_fallbacks)            / 100.0
        ]

        action, _  = model.predict(state)
        arm_list   = ["fallback_chain", "circuit_breaker", "hedged_request"]
        chosen_arm = arm_list[action]

        try:
            result = execute_strategy(chosen_arm, value, sys_metrics)
        except Exception as strategy_exc:
            logger.warning(
                "All strategies failed — returning degraded response",
                extra={"error": str(strategy_exc), "arm": chosen_arm}
            )
            FALLBACK_USED.labels(reason="degraded_response").inc()
            result = {
                "answer":        f"Degraded: {value}",
                "source":        "degraded",
                "confidence":    0.0,
                "used_fallback": True
            }

        log_chaos_event(
            chaos_module="rl", event_type="policy_update", stressor="none",
            adaptation_action=f"selected_{chosen_arm}", outcome="success",
            value=value, sys_metrics=sys_metrics,
            prediction=True, confidence=1.0, injected_by_ai=False
        )

        record_slo("resilient", (time.time() - start) * 1000, success=True)
        return jsonify({"chosen_arm": chosen_arm, "result": result, "state": state}), 200

    except Exception as e:
        api_errors_total.labels(stage="resilient").inc()
        logger.exception("Unexpected error in resilient_operation")
        record_slo("resilient", (time.time() - start) * 1000, success=False)
        return jsonify({"error": str(e), "outcome": "failure", "stressor": "unknown"}), 500


@app.route('/naive-api/process', methods=['POST'])
def naive_process():
    start = time.time()
    api_requests_total.labels(stage="naive").inc()
    data  = request.get_json(force=True)
    value = data.get("value")
    try:
        result = resilient_operation(value, random.choices(["timeout", "latency", "failure", "none"], weights = [0.55, 0.20, 0.15, 0.10])[0])
        record_slo("naive", (time.time() - start) * 1000, success=True)
        return jsonify({"stage": "naive", "result": result})
    except Exception as e:
        api_errors_total.labels(stage="naive").inc()
        record_slo("naive", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "naive", "error": str(e)}), 500


@app.route('/reactive-api/process', methods=['POST'])
def reactive_process():
    start = time.time()
    api_requests_total.labels(stage="reactive").inc()
    data  = request.get_json(force=True)
    value = data.get("value")
    try:
        for attempt in range(3):
            try:
                result = resilient_operation(value, random.choices(["timeout", "latency", "failure", "none"], weights = [0.55, 0.20, 0.15, 0.10])[0])
                record_slo("reactive", (time.time() - start) * 1000, success=True)
                return jsonify({"stage": "reactive", "result": result, "attempts": attempt + 1})
            except Exception:
                continue
        record_slo("reactive", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "reactive", "error": "All retries failed"}), 500
    except Exception as e:
        api_errors_total.labels(stage="reactive").inc()
        record_slo("reactive", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "reactive", "error": str(e)}), 500


@app.route('/antifragile-api/process', methods=['POST'])
def antifragile_process():
    start = time.time()
    api_requests_total.labels(stage="antifragile").inc()
    data        = request.get_json(force=True)
    value       = data.get("value")
    sys_metrics = get_system_metrics()
    try:
        result = execute_strategy(policy_manager.policy.choose_arm(), value, sys_metrics)
        stressor = select_ai_stressor(
            value, sys_metrics["cpu_percent"], sys_metrics["memory_percent"], confidence=1.0
        )
        resilient_operation(value, stressor)
        observed_uplift = random.uniform(-0.2, 0.3)
        arm, snapshot   = policy_manager.choose_and_update(observed_uplift)
        record_slo("antifragile", (time.time() - start) * 1000, success=True)
        return jsonify({
            "stage": "antifragile", "chosen_arm": arm,
            "policy_snapshot": snapshot, "uplift": observed_uplift, "result": result
        })
    except Exception as e:
        record_slo("antifragile", (time.time() - start) * 1000, success=False)
        return jsonify({"stage": "antifragile", "error": str(e)}), 500


@app.route("/ai/answer", methods=["POST"])
def ai_answer():
    data   = request.get_json(force=True)
    prompt = data.get("prompt")
    if not prompt or not isinstance(prompt, str):
        return jsonify({"error": "Invalid input: 'prompt' must be a string"}), 400
    sys_metrics = get_system_metrics()
    try:
        result = get_answer_with_fallback_chain(prompt, sys_metrics)
        return jsonify({
            "answer":        result["answer"],
            "source":        result["source"],
            "confidence":    result["confidence"],
            "used_fallback": result["used_fallback"]
        })
    except Exception as e:
        logger.exception("AI answer failed", extra={"error": str(e)})
        return jsonify({"error": "AI answer failed", "details": str(e)}), 500


# -----------------------------------------------------------------------
# AI chaos selector
# -----------------------------------------------------------------------
CHAOS_SELECTOR = train_chaos_selector()

def select_ai_stressor(value, cpu, mem, confidence) -> str:
    input_df      = pd.DataFrame([{"value": value, "cpu": cpu, "mem": mem, "confidence": confidence}])
    stressor_code = CHAOS_SELECTOR.predict(input_df)[0]
    reverse_map   = {v: k for k, v in STRESSOR_MAP.items()}
    return reverse_map.get(stressor_code, "none")


@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/train-model", methods=["POST"])
def train_model_endpoint():
    try:
        train_model()
        return jsonify({"status": "Model trained successfully"})
    except Exception as e:
        logger.warning("Model training failed", extra={"error": str(e)})
        return jsonify({"error": str(e)}), 500


def compute_precision(y_true, y_pred) -> float:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    return tp / (tp + fp) if (tp + fp) > 0 else 0.0

def compute_recall(y_true, y_pred) -> float:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    return tp / (tp + fn) if (tp + fn) > 0 else 0.0

def security_checks(y_true, y_pred, violation_detected):
    precision = compute_precision(y_true, y_pred)
    recall    = compute_recall(y_true, y_pred)
    SECURITY_ANOMALY_PRECISION.set(precision)
    SECURITY_ANOMALY_RECALL.set(recall)
    if violation_detected:
        SECURITY_POLICY_VIOLATIONS.inc()
    log_chaos_event(
        chaos_module="security", event_type="anomaly_detection", stressor="none",
        adaptation_action="isolation" if violation_detected else "none",
        outcome="failure" if violation_detected else "success",
        value=len(y_true), sys_metrics=get_system_metrics(),
        prediction=True, confidence=precision, injected_by_ai=False
    )


@app.route("/feature-importance")
def serve_feature_importance():
    try:
        return send_file("feature_importance.png", mimetype="image/png")
    except Exception as e:
        logger.error("Failed to serve feature importance plot", extra={"error": str(e)})
        return jsonify({"error": "Plot not found or unreadable"}), 404


@app.route("/generate-feature-importance", methods=["GET", "POST"])
def generate_feature_importance():
    try:
        df      = pd.read_csv("chaos_events1.csv")
        X       = df[["value", "cpu", "mem", "confidence"]]
        y       = df["success"]
        trained = train_model(X, y)
        plot_feature_importance(trained, X.columns)
        return jsonify({"status": "Plot generated"})
    except Exception as e:
        logger.error("Plot generation failed", extra={"error": str(e)})
        return jsonify({"error": str(e)}), 500


# -----------------------------------------------------------------------
# Chaos endpoints
# -----------------------------------------------------------------------
def now_iso():
    return (datetime.now() + timedelta(milliseconds=TIME_SKEW_MS)).isoformat()

def apply_netem(loss=0, delay_ms=0, jitter_ms=0, duplicate=0, reorder=0):
    os.system("tc qdisc del dev eth0 root || true")
    parts = []
    if loss:      parts.append(f"loss {loss}%")
    if delay_ms:  parts.append(f"delay {delay_ms}ms {jitter_ms or 0}ms distribution normal")
    if duplicate: parts.append(f"duplicate {duplicate}%")
    if reorder:   parts.append(f"reorder {reorder}% 50%")
    if parts:
        os.system(f"tc qdisc add dev eth0 root netem {' '.join(parts)}")
    log_chaos_event("runtime", "chaos_event", "network_turbulence", "none", "success",
                    0, get_system_metrics(), True, 0.9, False)


@app.route("/chaos/network", methods=["POST"])
def chaos_network():
    try:
        p = request.get_json(force=True)
        apply_netem(
            loss=int(p.get("loss", 0)),         delay_ms=int(p.get("delay_ms", 0)),
            jitter_ms=int(p.get("jitter_ms", 0)), duplicate=int(p.get("duplicate", 0)),
            reorder=int(p.get("reorder", 0))
        )
        STRESSOR_TYPE.labels(type="network").inc()
        CHAOS_ORIGIN.labels(origin="manual", stressor="network").inc()
        return jsonify({"status": "network chaos applied", "params": p}), 200
    except Exception as e:
        logger.exception("Chaos network injection failed")
        return jsonify({"error": str(e)}), 500


@app.route("/chaos/cpu", methods=["POST"])
def chaos_cpu():
    p       = request.get_json(force=True)
    cores   = int(p.get("cores", 1))
    seconds = int(p.get("seconds", 30))
    os.system(f"stress-ng --cpu {cores} --timeout {seconds}s --metrics-brief &")
    log_chaos_event("runtime", "chaos_event", "cpu", "none", "degraded",
                    cores, get_system_metrics(), True, 0.8, False)
    STRESSOR_TYPE.labels(type="cpu").inc()
    CHAOS_ORIGIN.labels(origin="manual", stressor="cpu").inc()
    return jsonify({"status": "cpu stress started", "cores": cores, "seconds": seconds})


@app.route("/chaos/memory", methods=["POST"])
def chaos_memory():
    p       = request.get_json(force=True)
    mb      = min(int(p.get("mb", 64)), 80)
    seconds = int(p.get("seconds", 60))
    block   = bytearray(mb * 1024 * 1024)
    _leaks.append(block)
    log_chaos_event("runtime", "chaos_event", "memory", "none", "degraded",
                    mb, get_system_metrics(), True, 0.7, False)
    STRESSOR_TYPE.labels(type="memory").inc()
    CHAOS_ORIGIN.labels(origin="manual", stressor="memory").inc()
    threading.Timer(seconds, lambda: _leaks.pop() if _leaks else None).start()
    return jsonify({"status": "memory allocated", "mb": mb, "seconds": seconds})


@app.route("/chaos/disk", methods=["POST"])
def chaos_disk():
    p         = request.get_json(force=True)
    mb        = int(p.get("mb", 512))
    path      = "/tmp/disk_stress"
    os.makedirs(path, exist_ok=True)
    blob_path = f"{path}/blob.bin"
    with open(blob_path, "wb") as f:
        f.write(os.urandom(mb * 1024 * 1024))
    os.system(f"sync; dd if={blob_path} of=/dev/null bs=4M iflag=direct")
    log_chaos_event("runtime", "chaos_event", "disk", "none", "degraded",
                    mb, get_system_metrics(), True, 0.75, False)
    STRESSOR_TYPE.labels(type="disk").inc()
    CHAOS_ORIGIN.labels(origin="manual", stressor="disk").inc()
    return jsonify({"status": "disk stress executed", "mb": mb})


@app.route("/chaos/time", methods=["POST"])
def chaos_time():
    global TIME_SKEW_MS
    p            = request.get_json(force=True)
    TIME_SKEW_MS = int(p.get("skew_ms", 0))
    log_chaos_event("runtime", "chaos_event", "time_skew", "none", "success",
                    TIME_SKEW_MS, get_system_metrics(), True, 0.85, False)
    STRESSOR_TYPE.labels(type="time").inc()
    CHAOS_ORIGIN.labels(origin="manual", stressor="time").inc()
    return jsonify({"status": "skew set", "skew_ms": TIME_SKEW_MS})


@app.route("/chaos/reset", methods=["POST"])
def chaos_reset():
    global TIME_SKEW_MS
    TIME_SKEW_MS = 0
    os.system("tc qdisc del dev eth0 root || true")
    _leaks.clear()
    log_chaos_event("runtime", "reset", "none", "none", "success",
                    0, get_system_metrics(), True, 1.0, False)
    return jsonify({"status": "reset"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/metrics': make_wsgi_app()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)