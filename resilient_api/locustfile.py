import random
from locust import HttpUser, task, between


def random_payload():
    return {"value": random.choice([10, 0, -5, 1.5, 7777777])}


class ResilientUser(HttpUser):
    wait_time = between(0.5, 3)
    host      = "http://app:5002"
    weight    = 3

    @task(3)
    def post_resilient(self):
        self.client.post("/resilient-api/process",
                         json=random_payload(), name="Resilient API")

    @task(2)
    def post_fragile(self):
        self.client.post("/fragile-api/process",
                         json=random_payload(), name="Fragile API")

    @task(2)
    def post_baseline(self):
        self.client.post("/baseline-api/process",
                         json=random_payload(), name="Baseline API")

    @task(2)
    def adaptive_data_processing(self):
        self.client.post(
            "/adaptive-api/process",
            json={"value": random.choice([10, 0, -5, 1.5, 100]),
                  "function_type": "data_processing"},
            name="Adaptive API - data_processing"
        )

    @task(2)
    def adaptive_llm_inference(self):
        self.client.post(
            "/adaptive-api/process",
            json={"value": random.choice([1, 5, 10, 50]),
                  "function_type": "llm_inference"},
            name="Adaptive API - llm_inference"
        )

    @task(2)
    def adaptive_realtime_query(self):
        self.client.post(
            "/adaptive-api/process",
            json={"value": random.choice([1, 2, 3, 5, 7]),
                  "function_type": "realtime_query"},
            name="Adaptive API - realtime_query"
        )

    @task(1)
    def adaptive_profile(self):
        self.client.get(
            "/adaptive-api/profile",
            name="Adaptive API - profile check"
        )