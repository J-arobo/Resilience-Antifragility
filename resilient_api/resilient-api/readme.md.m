import React from 'react';
import rdmd from '@readme/markdown';

export default ({ body }) => (
  <div className="markdown-body">
    {rdmd(body)}
  </div>
);

This system uses tenacity for retry logic and simulate a fragile dependency


1. Functional testing 
curl -X POST http://localhost:5002/resilient-api/process \
     -H "Content-Type: application/json" \
     -d '{"value": 10}'


2. Resislience Testing
for i in {1..20}; do
  curl -s -X POST http://localhost:5002/resilient-api/process \
       -H "Content-Type: application/json" \
       -d '{"value": 10}' | jq
done


3. Chaos & Stress Testing
pushng the system to its limits:
 3.1 Chaos Testing: Amplifying internaL Stressors
 our app already simulates:
 - Timeouts(TimeoutError)
 - Variable (time.sleep(random.unifrom(...)))
 - Random failures (raise Exception(...))
To intensify chaos:
- Increase failure probabilities temporarily:
    if random.random() < 0.7:  # instead of 0.3
    raise TimeoutError("Simulated timeout")
- adding new failure types:
    if random.random() < 0.2:
    raise MemoryError("Simulated memory spike")

    3.2 Stress Testing: External Load Simulation
    Using locust to simulate high traffic and traffic concurrent requests:

    To run:
    bash: "locust -f locustfile.py --host=http://localhost:5002"
    then on browser open:"http://localhost:8089" - to control load







"  
to run: docker-compose up --build

to tear down: docker-compose down

http://localhost:5002/metrics - metrics

http://localhost:5002/train-model - checking the training model

http://loki:3100 - url for adding a new data set

http://localhost:5002/generate-feature-importance - historgram

Query - resilient_chaos_origin_total{origin=~"ai|random"}

AI vs Random Injection Over Time	Time Series	resilient_chaos_origin_total{origin=~"ai|random"}

latency distribution use - sum(rate(resilient_latency_seconds_bucket[1m])) by (le, stressor)
"





 How chaos are applied
 1. internal chaos ijection (Code-Level)
    We are simulating failure directly inside our application logic:

    a. Random exceptions: Like your fragile_operation() raising TimeoutError or generic failures.

    b. Latency spikes: Injecting time.sleep() with randomized durations.

    c. Resource stress: Simulate memory or CPU pressure with dummy loops or large allocations.

    d. Dependency flakiness: Mock downstream services to intermittently fail or return corrupted data.

This is great for unit-level resilience testing.

2. External Chaos (Environment-Level)
we can simulate real-world infrastructure faults like:
    a. Network faults: tools like tc(linux) to add latency, packet loss or jitter:
    Bash
    tc qdisc add dev eth0 root netem delay 100ms loss 10%
    b. Container stress: Use stress-ng to simulate CPU, memory, I/O pressure:
    Bash
    stress-ng --cpu 2 --timeout 30s
    c. Kill services
    We can randomly stop containers or processes to test failover and recovery

3. Automated Chaos Experiment
 a. Custom scripts: You can write Python or Bash scripts to simulate outages, overloads, or misconfigurations.
 b. Chaos Monkey: Randomly kills services in production (Netflix-style).

c. Gremlin / Litmus / ChaosToolkit: Tools that orchestrate chaos experiments with observability hooks.







# Chaos Experiment done:
we have build a modular chaos experiment that randomly triggers stressors inside the Flask API and logs fallback behaviour. this scaffold will simulate unpredictable conditions, observe how the system responds and narrate its resillience story though logs.
Chaos Experiment Goals
Randomly trigger timeouts, latency, and failures in fragile_operation()

Log which stressor was triggered

Log whether the retry succeeded or fallback was used

Keep the structure clean and extensible for future metrics or visualizations

How to Run the Experiment
Start your Flask app (via Docker or manually)

Use Locust or a script to send varied requests:

bash
curl -X POST http://localhost:5002/resilient-api/process \
     -H "Content-Type: application/json" \
     -d '{"value": 10}'
Observe console output:

[CHAOS] Triggered timeout

[FALLBACK] Retry failed. Fallback result used.

[SUCCESS] Operation completed with result: 20




- to run python sript: python chaos_test.py



# Added structured logging to be able to narrate the resilience.
- using python-json-logger to format logs as JSON - making them machine readable and ready for ingestion by tools, like Fluentd, Loki or Prometheus

N/B: 
We are using both locust and script to simulate requests and apply stress on our flask API





What we are adding
1. Behavioral learning from Chaos Events
Instead of just logging chaos injections, i use them to train lightweight models that predict failure patterns or recommend fallback strategies.
 - learning.py - module that handles:
      a. Feature extraction from logs
      b. Model training
      c. Prediction of fallback sucess

2. AI driven chaos injections
    Instead of randomly choosing stressors, your system uses a model to:

    Predict which stressor is most likely to cause failure

    Inject that stressor to test resilience

    Learn from the outcome and refine future injections

    This turns chaos into a targeted diagnostic tool—like a doctor probing for symptoms, not just throwing punches.


To do:
- visualise all the modules - e.g, AI vs Random Chaos Effectiveness in Grafana



AI DRIVEN CHAOS INJECTIONS









"""
What The CSV Rows Represent
stressor: Type of chaos injected (none, latency, failure, timeout)

value: Input value sent to the API

result: Output or fallback result (use -1 if operation failed completely)

success: 1 if operation succeeded, 0 if it failed

fallback_used: 1 if fallback logic was triggered

cpu, mem: System metrics at time of request

prediction: Model’s prediction (1 for success, 0 for failure)

confidence: Model’s confidence score (0–1)

injected_by_ai: 1 if stressor was chosen by AI, 0 if random
"""



What We’ll Visualize
You’ve already got structured logs with injected_by_ai, stressor, fallback_used, and confidence. Let’s turn those into panels that answer:

How often does AI choose each stressor?

Does AI injection lead to more fallbacks (i.e. smarter probing)?

How does prediction confidence correlate with fallback usage?





To solve 

1. change the accuracy - ##Done
1. show the plotted plot.✅ 
3. plot the various panels in grafana.
4. why used_ai = 0 and not 1
5. log in injected by AI
1. It gives me a number multiplied by 1/2 every time

After waking up , start with the plot solution then go to panel drain

✅ M