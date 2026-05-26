import requests
import random
import time

URL = "http://localhost:5002/resilient-api/process"

def generate_payload():
    return {"value": random.choice([10, 0, -5, 1.5, 999999, "invalid", None])}

for i in range(50):  # Send 50 requests
    payload = generate_payload()
    try:
        response = requests.post(URL, json=payload)
        print(f"[{i+1}] Sent: {payload} | Status: {response.status_code} | Response: {response.json()}")
    except Exception as e:
        print(f"[{i+1}] Error sending request: {e}")
    time.sleep(random.uniform(0.2, 1.0))  # Random delay between requests
