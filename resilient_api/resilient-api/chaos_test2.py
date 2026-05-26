import requests
import random
import time

API_URL = "http://localhost:5002/process-data"  # Adjust if needed

for i in range(20):
    payload = {
        "value": random.randint(10, 100),
        "cpu": round(random.uniform(5.0, 90.0), 2),
        "mem": round(random.uniform(10.0, 95.0), 2),
        "confidence": round(random.uniform(0.3, 0.95), 2)
    }
    try:
        response = requests.post(API_URL, json=payload)
        print(f"[{i+1}] Chaos injected → Status: {response.status_code}")
    except Exception as e:
        print(f"[{i+1}] Injection failed → {e}")
    time.sleep(0.2)  # Optional: slow down to simulate real traffic
