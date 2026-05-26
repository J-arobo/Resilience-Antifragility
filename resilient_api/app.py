from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
import random
import time

app = Flask(__name__)

# Simulated fragile dependency with stressors
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def fragile_operation(value):
    stressor = random.choice(["timeout", "latency", "failure", "none"])

    if stressor == "timeout":
        print("[CHAOS] Triggered timeout")
        raise TimeoutError("Simulated timeout")

    elif stressor == "latency":
        latency = random.uniform(0.5, 2.0)
        print(f"[CHAOS] Triggered latency: {latency:.2f}s")
        time.sleep(latency)

    elif stressor == "failure":
        print("[CHAOS] Triggered failure")
        raise Exception("Simulated failure")

    time.sleep(0.2)  # Base latency
    result = value * 2
    print(f"[SUCCESS] Operation completed with result: {result}")
    return result


@app.route('/resilient-api/process', methods=['POST'])
def process_data():
    try:
        data = request.get_json(force=True)
        value = data.get("value")
        print(f"[REQUEST] Received value: {value}")

        if value is None or not isinstance(value, (int, float)):
            print("[VALIDATION] Invalid input")
            return jsonify({"error": "Invalid input: 'value' must be a number"}), 400

        try:
            result = fragile_operation(value)
            print("[RETRY] Operation succeeded after retry")
            return jsonify({
                "result": result,
                "retries_used": True
            })
        except RetryError:
            fallback_result = value * 1.5
            print("[FALLBACK] Retry failed. Fallback result used.")
            return jsonify({
                "warning": "Dependency failed after retries. Fallback used.",
                "result": fallback_result,
                "retries_used": False
            }), 200

    except Exception as e:
        print(f"[ERROR] Unhandled exception: {str(e)}")
        return jsonify({"error": f"Internal error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
