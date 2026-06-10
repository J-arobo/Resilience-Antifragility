#BanditPolicy class is the adaptive decision making logic in the continuous learning lop.
#it belogs in its own module so it can keep the orchestration(experiments), metrics and persistence separate.
import random

class BanditPolicy:
    def __init__(self, arms):
        # Initialize each arm with equal weight
        self.weights = {arm: 1.0 for arm in arms}

    def update_weights(self, arm, uplift):
        """
        Update the weight of a given arm based on uplift score.
        Positive uplift → increase weight, negative uplift → decrease.
        """
        self.weights[arm] *= (1 + uplift)

        # Normalize weights so they sum to 1
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] /= total

    def choose_arm(self):
        """
        Select an arm (strategy) based on current weights.
        Weighted random choice ensures higher-weight arms are more likely.
        """
        arms = list(self.weights.keys())
        probs = list(self.weights.values())
        return random.choices(arms, weights=probs, k=1)[0]

    def get_policy_snapshot(self):
        """
        Return current weights for logging or visualization.
        """
        return dict(self.weights)

"""

🔄 How It Connects
🔄 How It Works
update_weights(): adjusts probabilities after each chaos experiment.

choose_arm(): picks a resilience strategy (e.g., fallback chain, circuit breaker, hedged request) based on updated weights.

get_policy_snapshot(): lets you log or version the current policy state.
"""