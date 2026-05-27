
from chaos.bandit import BanditPolicy
from chaos.experiments import run_chaos_experiment
from chaos.policy_manager import save_policy_version

# Initialize bandit with resilience strategies
bandit = BanditPolicy(["fallback_chain", "circuit_breaker", "hedged_request"])

# Define chaos experiments to run in sequence
chaos_experiments = {
    "packet_loss": "tc qdisc add dev eth0 root netem loss 20%",
    "latency": "tc qdisc add dev eth0 root netem delay 200ms",
    "cpu_stress": "stress --cpu 2 --timeout 30",
    "memory_pressure": "stress --vm 1 --vm-bytes 256M --timeout 30"
}

version_id = 1

for experiment_name, command in chaos_experiments.items():
    print(f"\n=== Running chaos experiment: {experiment_name} ===")

    # Run chaos experiment and compute uplift
    uplift = run_chaos_experiment(experiment_name, command)
    print(f"Uplift score for {experiment_name}: {uplift:.2f}")

    # Update bandit weights based on uplift
    # (refine mapping logic later if needed)
    arm = "hedged_request" if experiment_name == "packet_loss" else "fallback_chain"
    bandit.update_weights(arm, uplift)

    # Choose next strategy adaptively
    selected_strategy = bandit.choose_arm()
    print("Selected strategy:", selected_strategy)

    # Save snapshot for versioning
    snapshot = bandit.get_policy_snapshot()
    print("Current weights:", snapshot)
    save_policy_version(bandit, version_id)

    version_id += 1

print("\n=== Continuous learning loop complete ===")



"""

🔄 How It Connects
run_loop.py is your entry point — run it manually or schedule it (cron/CI/CD).

It imports the bandit, runs chaos experiments, updates weights, and saves policy versions.

Over time, you’ll have a log of uplift scores and evolving policy snapshots.
"""



"""
🔄 What This Does
Iterates through a set of chaos experiments (packet loss, latency, CPU stress, memory pressure).

Runs each experiment → collects metrics → computes uplift.

Updates bandit weights based on uplift.

Chooses the next strategy adaptively.

Saves a new policy version after each experiment.
"""