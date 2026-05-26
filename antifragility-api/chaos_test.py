import requests
import random
import time
import logging
from pythonjsonlogger import jsonlogger

# Structured logger setup
logger = logging.getLogger("chaos_client")
logger.setLevel(logging.INFO)

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s %(extra)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

URL = {
    #"naive": "http://localhost:5000/naive-api/process", #port 5001
    #"reactive": "http://localhost:5004/reactive-api/process", #port 5004
    #"resilient": "http://localhost:5002/resilient-api/process", #port 5002
    "antifragile": "http://localhost:5005/antifragile-api/process" #port 5005

}

def generate_payload():
    return {"value": random.choice([10, 0, -5, 1.5, 999999, "invalid", None])}

for i in range(3):  # Send 50 requests
    payload = generate_payload()
    try:
        response = requests.post(URL["antifragile"], json=payload)
        #print(f"[{i+1}] Sent: {payload} | Status: {response.status_code} | Response: {response.json()}")
        #Using logger insead of print
        logger.info("Request sent", extra={
            "iteration": i + 1,
            "payload": payload,
            "status_code": response.status_code,
            "response": response.json() 
        })
    except Exception as e:
        #print(f"[{i+1}] Error sending request: {e}")
        #using logger instead
        logger.error("Request failed", extra={
            "iteration": i + 1,
            "payload": payload,
            "error": str(e)
        })
    time.sleep(random.uniform(0.2, 1.0))  # Random delay between requests
