import random
from locust import HttpUser, task, between

class ResilientUser(HttpUser):
    #wait_time = between(1, 3)  # Simulates user think time
    #Random dalay between tasks to simulate user think time
    wait_time = between(0.5, 3)

    @task
    def post_random_payload(self):
        #Simulate varied payloads
        payload = {
            "value": random.choice([
                10,
                0,
                -5,
                1.5,
                7777777,
                "invalid", #Triggers validation error
                None        #Triggers missing value
            ])
        }
        
        #Log the payload being sent
        print(f"Sending payload: {payload}")

        self.client.post("/resilient-api/process", json=payload)
