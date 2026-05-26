# naive_api.py
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/naive-api/process", methods=["POST"])
def process():
    data = request.get_json()
    value = data.get("value", 0)
    try:
        result = value * 2
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)



'''
What makes it naive?
- No input validation
- No exception handling
- Single-threaded, no retries
- Fails on bad input or unexpected request format
'''








