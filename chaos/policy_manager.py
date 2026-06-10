# policy_manager.py
from .bandit import BanditPolicy
from .experiments import run_experiment
from .metrics import record_bandit_metrics

class PolicyManager:
    def __init__(self, arms):
        self.policy = BanditPolicy(arms)

    def choose_and_update(self, observed_uplift):
        arm = self.policy.choose_arm()
        snapshot = run_experiment(self.policy, arm, observed_uplift)
        record_bandit_metrics(arm, observed_uplift)
        return arm, snapshot
