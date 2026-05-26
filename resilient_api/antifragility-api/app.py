from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, retry_if_exception_type wait_fixed, RetryError, wait_exponential
import random, time, logging
from pythonjsonlogger import jsonlogger
from datetime import datetime
from prometheus_client import Counter, Histogram,  generate_latest, CONTENT_TYPE_LATEST

#Metrics
REQUEST_COUNT = Counter("antifragile_requests_total", "Total requests received")
RETRY_SUCCESS = Counter("antifragile_retry_success_total", "Successful retries")
FALLBACK_USED = Counter("antifragile_fallback_total", "Fallbacks triggered")
STRESSOR_TYPE = Counter("antifragile_stressor_type_total", "Stressor type triggered", ["type"])
LATENCY_HISTOGRAM = Histogram("antifragile_latency_seconds", "Latency injected by chaos")


# Adding structured logging
logger = logging.getLogger("antifragile")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(extra)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

app = Flask(__name__)

# Chaos-aware operation
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def antifragile_operation(value):
    stressor = random.choice([ "timeout", "latency", "failure", "none"])
    metadata = {"value": value, "stressor": stressor}

    logger.warning("Chaos injected", extra={
        "timestamp": time.time(),
        "stressor": stressor,
        "value": value
    })

    if stressor == "timeout":
        logger.warning("Antifragile: Timeout triggered", extra=metadata)
        raise TimeoutError("Simulated timeout")

    elif stressor == "latency":
        latency = random.uniform(0.5, 2.0)
        metadata["latency"] = latency
        logger.info("Antifragile: Latency injected", extra=metadata)
        time.sleep(latency)

    elif stressor == "failure":
        logger.error("Antifragile: Failure triggered", extra=metadata)
        raise Exception("Simulated failure")

    time.sleep(0.2)
    result = value * 2
    metadata["result"] = result
    logger.info("Antifragile: Operation succeeded", extra=metadata)
    return result

@app.route("/antifragile-api/process", methods=["POST"])
def process():
    try:
        data = request.get_json(force=True)
        value = data.get("value")
        logger.info("Antifragile: Request received", extra={"value": value})

        if value is None or not isinstance(value, (int, float)):
            logger.warning("Antifragile: Invalid input", extra={"input": data})
            return jsonify({"error": "Invalid input"}), 400

        try:
            result = antifragile_operation(value)
            logger.info("Antifragile: Retry succeeded", extra={"result": result})
            return jsonify({"result": result, "retries_used": True})
        except RetryError:
            fallback_result = value * 1.5
            logger.warning("Antifragile: Fallback used after retries failed", extra={"fallback_result": fallback_result})
            return jsonify({
                "warning": "Fallback triggered after retries",
                "result": fallback_result,
                "retries_used": False
            }), 200

    except Exception as e:
        logger.exception("Antifragile: Unhandled exception", extra={"error": str(e)})
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


#To view metrics
@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

if __name__ == "__main__":
    app.run(port=5005)

