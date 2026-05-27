from flask import Blueprint, request, jsonify
from metrics import api_requests_total, api_errors_total

reactive_bp = Blueprint("reactive", __name__)

@reactive_bp.route("/reactive-api/process", methods=["POST"])
def process():
    api_requests_total.labels(stage="reactive").inc()
    data = request.get_json()
    value = data.get("value", 0)
    try:
        if value == "invalid" or value is None:
            raise ValueError("Invalid input")
        result = value * 2
        return jsonify({"result": result})
    except Exception as e:
        api_errors_total.labels(stage="reactive").inc()
        fallback_result = value * 1.5 if isinstance(value, (int, float)) else None
        return jsonify({
            "warning": "Reactive fallback triggered",
            "fallback_result": fallback_result,
            "error": str(e)
        }), 200

"""
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/reactive-api/process", methods=["POST"])
def process():
    data = request.get_json()
    value = data.get("value", 0)

    try:
        # Simulate fragile operation
        if value == "invalid" or value is None:
            raise ValueError("Invalid input")

        result = value * 2
        return jsonify({"result": result})
    except Exception as e:
        fallback_result = value * 1.5 if isinstance(value, (int, float)) else None
        return jsonify({
            "warning": "Reactive fallback triggered",
            "fallback_result": fallback_result,
            "error": str(e)
        }), 200

if __name__ == "__main__":
    app.run(port=5004)
"""

