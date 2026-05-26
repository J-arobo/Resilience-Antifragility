# app.py
import logging
logger = logging.getLogger(__name__)


def execute_chaos(stressor):
    try:
        # Simulate the stressor
        if stressor == "timeout":
            time.sleep(2)  # simulate delay
        elif stressor == "latency":
            _ = [x**2 for x in range(1000000)]  # simulate CPU load
        elif stressor == "failure":
            raise RuntimeError("Simulated failure")
        elif stressor == "none":
            pass  # no stressor applied
        return False  # no fallback triggered
    except Exception as e:
        # Fallback logic here (e.g., default response, retry, etc.)
        logger.warning("Fallback triggered due to chaos", extra={"error": str(e)})
        return True  # fallback was used
