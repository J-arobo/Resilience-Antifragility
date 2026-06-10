# metrics.py
from prometheus_client import Counter, Gauge

BANDIT_ARM_CHOSEN = Counter("bandit_arm_chosen_total", "Arms chosen by bandit", ["arm"])
BANDIT_UPLIFT = Gauge("bandit_uplift_score", "Observed uplift score per arm", ["arm"])

def record_bandit_metrics(arm, uplift):
    BANDIT_ARM_CHOSEN.labels(arm=arm).inc()
    BANDIT_UPLIFT.labels(arm=arm).set(uplift)
