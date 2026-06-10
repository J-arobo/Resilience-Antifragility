# run chaos_experiment
#Automating Chaos experiment
#wrapping them in a runner
# experiments.py
from .bandit import BanditPolicy

def run_experiment(policy: BanditPolicy, arm, observed_uplift):
    # Update weights based on experiment outcome
    policy.update_weights(arm, observed_uplift)
    return policy.get_policy_snapshot()

#to be chnaged
def execute_chaos(policy_manager, observed_uplift):
    """
    Run a chaos experiment using the given PolicyManager.
    """
    arm, snapshot = policy_manager.choose_and_update(observed_uplift)
    return {"arm": arm, "snapshot": snapshot}







"""
🔄 How It Runs
Your API (app.py) exposes metrics to Prometheus.

experiments.py triggers chaos (e.g., packet loss via tc).

metrics.py collects baseline and post‑chaos metrics.

experiments.py computes uplift and logs results.

bandit.py updates weights based on uplift.

policy_manager.py versions the updated policy.
"""
