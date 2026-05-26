from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
import random
import time
import psutil
import pandas as pd
import logging
from datetime import datetime, timezone
from pythonjsonlogger import jsonlogger
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from learning import train_model, plot_feature_importance
from learning import predict_with_confidence, log_chaos_to_csv
#AI chaos
from learning import train_chaos_selector
#For viewing the plot at an endpoint
from flask import send_file
from chaos import execute_chaos





#Stressor map for the select_ai_stressor function
STRESSOR_MAP = {
    "timeout": 0,
    "latency": 1,
    "failure": 2,
    "none": 3
}

#Metric of chaos injected by ai 


# Metrics
CHAOS_ORIGIN = Counter(
    "resilient_chaos_origin_total",
    "Counts chaos injections by origin",
    ["origin", "stressor"]
)
AI_INJECTED = Counter("resilient_ai_injected_total", "AI-driven chaos injections", ["stressor"])
RANDOM_INJECTED = Counter("resilient_random_injected_total", "Random chaos injections", ["stressor"])

FALLBACK_TOTAL = Counter("reactive_fallback_total", "Total fallback events triggered during chaos")
RETRY_SUCCESS = Counter("resilient_retry_success_total", "Successful retries")
FALLBACK_USED = Counter("resilient_fallback_total", "Fallbacks triggered")
STRESSOR_TYPE = Counter("resilient_stressor_type_total", "Stressor type triggered", ["type"])
LATENCY_HISTOGRAM = Histogram(
    "resilient_latency_seconds", 
    "Latency injected by chaos",
    #buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    )
RESILIENT_REQUESTS = Counter("resilient_requests_total", "Total number of requests processed by the resilient API")

"""
REQUEST_COUNT = Counter("resilient_requests_total", "Total requests received")
RETRY_SUCCESS = Counter("resilient_retry_success_total", "Successful retries")
FALLBACK_USED = Counter("resilient_fallback_total", "Fallbacks triggered")
STRESSOR_TYPE = Counter("resilient_stressor_type_total", "Stressor type triggered", ["type"])
LATENCY_HISTOGRAM = Histogram("resilient_latency_seconds", "Latency injected by chaos")
"""
# Adding structured logging
logger = logging.getLogger("locust_logger")
logger.setLevel(logging.INFO)

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(extra)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

app = Flask(__name__)

def get_system_metrics():
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent
    }

# Simulated fragile dependency with stressors
@retry(stop=stop_after_attempt(5), wait=wait_fixed(0.5))
def resilient_operation(value, stressor):
    #stressor = random.choice(["timeout", "latency", "failure", "none"])
    STRESSOR_TYPE.labels(type=stressor).inc()

    logger.warning("Chaos injected", extra={
    "timestamp": datetime.utcnow().isoformat(),
    "stressor": stressor,
    "value": value
    })


    if stressor == "timeout":
        logger.warning("Trigerred timeout", extra={"stressor": stressor, "value": value})
        raise TimeoutError("Simulated timeout")

    elif stressor == "latency":
        latency = random.uniform(0.5, 2.0)
        #print(f"[CHAOS] Triggered latency: {latency:.2f}s")
        #logger.info("Triggered latency", extra={"stressor": stressor, "latency": latency, "value":value})
        LATENCY_HISTOGRAM.observe(latency)
        time.sleep(latency)

    elif stressor == "failure":
        #print("[CHAOS] Triggered failure")
        #logger.error("Triggered failure", extra={"stressor": stressor, "value":value})
        raise Exception("Simulated failure")

    time.sleep(0.2)  # Base latency
    result = value * 2
    #print(f"[SUCCESS] Operation completed with result: {result}")
    logger.info("Operation succeeded", extra={"result":result, "value": value})
    return result


@app.route('/resilient-api/process', methods=['POST'])
def process_data():
    #To sned the metric
    RESILIENT_REQUESTS.inc()

    data = request.get_json(force=True)
    value = data.get("value")

    if value is None or not isinstance(value, (int, float)):
        logger.warning("Invalid input", extra={"input": data})
        return jsonify({"error": "Invalid input: 'value' must be a number"}), 400

    #stressor = random.choice(["timeout", "latency", "failure", "none"]) 
    #stressor = select_ai_stressor(value, sys_metrics["cpu_percent"], sys_metrics["memory_percent"], confidence)
    #injected_by_ai = True

    sys_metrics = get_system_metrics()
    logger.info("System metrics", extra=sys_metrics)

    cpu = sys_metrics["cpu_percent"]
    mem = sys_metrics["memory_percent"]


    # Predict success and confidence
    try:
        #stressor = select_ai_stressor(value, cpu, mem, confidence)
        prediction, confidence = predict_with_confidence(
            #stressor, value, 
            "none", value,    #Used none temporarily for prediction
            cpu, 
            mem)
    except Exception as e:
        logger.exception("Prediction failed", extra={"error":str(e)})
        confidence = 0.5   #Assigning a default value to avoid crushing
        prediction = True
        #logger.info("Prediction", extra={"stressor": stressor, "value": value, "prediction": prediction, "confidence": confidence})
        #return jsonify({"error": "Prediction failed", "details": str(e) }), 500
        logger.warning("Using default prediction due to failure", extra={"confidence": confidence})

    #AI driven chaos selection
    try:
        stressor = select_ai_stressor(value, cpu, mem, confidence)
        injected_by_ai = True
    except Exception as e:
        stressor = random.choice(["timeout", "latency", "failure", "none"])
        injected_by_ai = False
        logger.warning("AI chaos selector failed, falling back to random", extra={"error": str(e)})

    # Execute chaos and capture fallback status
    fallback_used = execute_chaos(stressor)

    # Increment Prometheus metric if fallback occurred
    if fallback_used:
        FALLBACK_TOTAL.inc()

    #Prometheus counters for chaos logic
    if injected_by_ai:
        AI_INJECTED.labels(stressor=stressor).inc()
    else:
        RANDOM_INJECTED.labels(stressor=stressor).inc()

    #To increment the counter for each chaos event, tagged by origin and stressor type
    origin = "ai" if injected_by_ai else "random"
    CHAOS_ORIGIN.labels(origin=origin, stressor=stressor).inc()

    logger.info("Chaos event", extra={
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value": value,
        "confidence": confidence,
        "fallback_used": fallback_used,
        "stressor": stressor,
        "injected_by_ai": injected_by_ai
    })


    ##Behavioral
    #stressor = random.choice(["timeout", "latency", "failure", "none"])
    #predicted_success = predict_success(stressor, value)
    #logger.info("Predicted success", extra={"stressor": stressor, "value": value, "prediction": predicted_success})

    try:
        result = resilient_operation(value, stressor)
        RETRY_SUCCESS.inc()
        log_chaos_to_csv(
            stressor=stressor,
            value=value,
            result=result,
            success=True,
            fallback_used=False,
            cpu=sys_metrics["cpu_percent"],
            mem=sys_metrics["memory_percent"],
            prediction=prediction,
            confidence=confidence,
            injected_by_ai = injected_by_ai
        )
        #logger.info("Retry succeeded", extra={"result": result})
        return jsonify({"result": result, "retries_used": True, "confidence": confidence})
    except RetryError:
        fallback_result = value * 1.5
        FALLBACK_USED.inc()
        log_chaos_to_csv(
            stressor=stressor,
            value=value,
            result=fallback_result,
            success=True,
            fallback_used=True,
            cpu=sys_metrics["cpu_percent"],
            mem=sys_metrics["memory_percent"],
            prediction=prediction,
            confidence=confidence,
            injected_by_ai = injected_by_ai
        )
        #logger.warning("Fallback used after retries failed", extra={"fallback_result": fallback_result})
        return jsonify({"warning": "Fallback used after retries failed.", "result": fallback_result, "retries_used": False, "confidence": confidence}), 200
    except Exception as e:
        log_chaos_to_csv(
            stressor=stressor,
            value=value,
            result=None,
            success=False,
            fallback_used=False,
            cpu=sys_metrics["cpu_percent"],
            mem=sys_metrics["memory_percent"],
            prediction=prediction,
            confidence=confidence,
            injected_by_ai = injected_by_ai
        )
        logger.exception("Unhandled exception", extra={"error": str(e)})
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


#Chaos selector using AI
CHAOS_SELECTOR = train_chaos_selector()

def select_ai_stressor(value, cpu, mem, confidence):
    input_df = pd.DataFrame([{
        "value": value,
        "cpu": cpu,
        "mem": mem,
        "confidence": confidence
    }])
    stressor_code = CHAOS_SELECTOR.predict(input_df)[0]
    reverse_map = {v: k for k, v in STRESSOR_MAP.items()}
    return reverse_map.get(stressor_code, "none")

#Metrics endpoint
@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


#Train-model end point
@app.route("/train-model", methods=["POST"])
def train_model_endpoint():
    try:
        train_model()
        return jsonify({"status": "Model trained successfully"})
    except Exception as e:
        logger.warning("Model training failed", extra={"error": str(e)})
        return jsonify({"error": str(e)}), 500 # Default optimistic guess


    """
    try:
        train_model()
        return jsonify({"status": "Model trained successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        """

#for viewing the plot
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
        #step 1: Load and prepare traiing data 
        df = pd.read_csv("chaos_events1.csv")
        X = df[["value", "cpu", "mem", "confidence"]]  #My actual features
        y = df["success"]      #Target variable

        #Training the model
        model = train_model(X, y)
        plot_feature_importance(model, X.columns)

        #step 3: plotting feature importance using correct feature names
        #feature_names = ["value", "cpu", "mem", "confidence"]
        #print("[DEBUG] Plotting feature importance")

        return jsonify({"status": "Plot generated"})
    except Exception as e:
        logger.error("Plot generation failed", extra={"error": str(e)})
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
