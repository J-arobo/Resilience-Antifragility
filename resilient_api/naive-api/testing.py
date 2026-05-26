
#API layer - Naive Implementation

from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# HTML form for browser testing
@app.route('/')
def home():
    return render_template_string('''
        <h2>Test Naive API</h2>
        <form action="/naive-api/process" method="post">
            <label>Value:</label>
            <input type="number" name="value">
            <button type="submit">Submit</button>
        </form>
    ''')

@app.route('/naive-api/process', methods=['POST'])
def process_data():
    if not request.is_json:
        return jsonify({"error": "Request mmust be JSON"}), 400
    
    data = request.get_json()
    if "value" not in data:
        return jsonify({"error": "'value' field is required"}), 400
    
    try: 
        result = float(data["value"]) * 2
    except (ValueError, TypeError):
        return jsonify({"error": "'value' must be a number"}), 400
    
    #data = request.json
    # Naively assumes input is always valid
    #result = data["value"] * 2  # This will crash if 'value' is missing or not a number
    #return jsonify({"result": result})

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=8080)
    #We are running on port 8080 - to accesss http://172.17.0.2:8080
