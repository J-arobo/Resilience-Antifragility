from prometheus_client import Counter

# Define counters once, globally
api_requests_total = Counter("api_requests_total", "Total API requests", ["stage"])
api_errors_total = Counter("api_errors_total", "Total API errors", ["stage"])
"""
API_REQUESTS = Counter(
    "api_requests_total",
    "Total requests processed",
    ["stage"]
)
"""