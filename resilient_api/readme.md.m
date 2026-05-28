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

To do: Find the other end points
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


"""
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

05/08/25
to address:
1. Accessing the endpoints - ✅ 
1. CSV file in cloud - accessing and saving it. - ✅ 

After waking up , start with the plot solution then go to panel drain

✅ 


"""
MY ENDPOINTS
locust - http://localhost:8090
Grafana - http://localhost:3001
Parometheus - http://localhost:9090
Loki - checking if its ready - http://localhost:3100/ready
Metrics - http://localhost:5002/metrics
"""


"http://13.60.196.175:3001/d/resilient-api/resilient-api-observability?orgId=1&from=now-6h&to=now&timezone=browser&refresh=10s

http://13.60.196.175:8090/

http://13.60.196.175:3100/ready

http://13.60.196.175:9090/query?g0.expr=resilient_ai_injected_total&g0.show_tree=0&g0.tab=table&g0.end_input=2025-10-02+13%3A25%3A46&g0.moment_input=2025-10-02+13%3A25%3A46&g0.range_input=1h&g0.res_type=auto&g0.res_density=medium&g0.display_mode=lines&g0.show_exemplars=0&g1.expr=resilient_ai_injected_created&g1.show_tree=0&g1.tab=table&g1.range_input=1h&g1.res_type=auto&g1.res_density=medium&g1.display_mode=lines&g1.show_exemplars=0&g2.expr=&g2.show_tree=0&g2.tab=table&g2.range_input=1h&g2.res_type=auto&g2.res_density=medium&g2.display_mode=lines&g2.show_exemplars=0

http://13.60.196.175:5002/metrics

"


# New Ones
http://13.60.196.175:5002/metrics
13.53.193.146:
http://13.53.193.146:5002/metrics



CHAOS EVENT LOG SCHEMA

{
  "timestamp": "2025-12-09T21:42:00Z",
  "level": "INFO",                // Log severity: INFO, WARNING, ERROR
  "module": "retrieval",          // Which subsystem: llm, retrieval, api, runtime, security
  "event_type": "chaos_event",    // Type of log: chaos_event, fallback, retry, anomaly, system_metric
  "stress_class": "latency",      // Stressor applied: timeout, latency, failure, none
  "adaptation_action": "fallback",// Adaptive response: retry, fallback, circuit_breaker, cache_fallback
  "outcome": "success",           // Outcome: success, failure, degraded
  "chaos_event_id": "evt-12345",  // Unique ID for correlation across metrics/logs/traces
  "value": 42,                    // Input value or payload processed
  "latency_ms": 120,              // Measured latency (if applicable)
  "cpu_percent": 65.3,            // System CPU usage at event time
  "memory_percent": 72.1,         // System memory usage at event time
  "prediction": true,             // AI prediction outcome
  "confidence": 0.87,             // AI confidence score
  "injected_by_ai": true          // Origin of chaos: true (AI) or false (random)
}






To add later:

"Add Loki as a data source (http://loki:3100).

Query logs with filters:

{app="resilient-api"} |= "Chaos event"

{level="warning"} |= "Chaos injected"

Overlay logs as annotations on your Prometheus panels (you already have this in your dashboard JSON)."

Promtail will scrape these logs, ship them to Loki, and Grafana can query them with filters like {module="retrieval"} |= "Chaos event"

  10/12/25
  To add
  1. #To replace task_queue with my actual queue
  2. violation_detected = False  # replace with real policy check
  3. Would you like me to draft simple helper implementations for compute_precision and compute_recall so you can drop them in and have working metrics right away?
  4. AWS Security Group rules: Temporarily block or throttle traffic between services.

  
"
Next step: once Prometheus is scraping these jobs, you can build Grafana dashboards that combine chaos metrics with system health.
 For example: overlay resilient_latency_seconds_bucket with node_cpu_seconds_total to see how latency spikes correlate with CPU pressure."


✅ Why Prometheus Scrape Config matters
Scraping resilient-api gives you chaos metrics (resilient_requests_total, resilient_latency_seconds, etc.).

Scraping node exporter gives you CPU/memory/disk metrics to correlate with chaos events.

Scraping Loki/Promtail lets you monitor log ingestion health.

Scraping Grafana lets you monitor dashboard uptime.

Scraping OTel collector prepares you for traces if you add them later.

✅ Summary
Call log_chaos_event() after each major stage: retrieval, prediction, stressor selection, chaos execution, retry/fallback, and error handling.

This replaces the ad‑hoc logger.info("Chaos event", extra={...}) calls with a uniform schema.

Loki will now index logs with consistent fields (module, event_type, stress_class, adaptation_action, outcome, etc.), making Grafana queries and annotations straightforward.

"Would you like me to rewrite your process_data() function with these log_chaos_event() calls already inserted, so you can copy‑paste the full updated version?"

"Would you like me to also show how to query these success path logs in Grafana Loki (e.g. {event_type="success_path"}) so you can visualize them as annotations on your latency/CPU panels?"


CHAOS ENGINEERING HOOKS INTRODUCED
Excellent — let’s break down Chaos Engineering Hooks into actionable steps you can implement in your antifragility stack. These hooks let you deliberately
introduce stress into your system and then observe how your metrics/logs respond in Prometheus, Loki, and Grafana.

1. Network Turbulence (Packet Drops)
Docker Compose healthchecks: Add a healthcheck to simulate degraded networking.

AWS Security Group rules: Temporarily block or throttle traffic between services.
(Done in Docker Compose. - The Health checks - down)

2. Latency Spikes (Artificial Delays)
- Injecting Delays directly in the API logic (already did in resilient_operation() ).
- Alternatively, using netem to add latency at the container level e.g:
    tc qdisc add dev eth0 root netem delay 200ms 50ms distribution normal
    - this adds 200ms average latency with 50ms jitter

3. Resource pressure (CPU/Memory Quotas)
Using Docker Compose resource imits to constraint containers
Simulate CPU/memory pressure to test resillience.


4. Implementing Systematic chaos scenariosStep 1: Define Chaos Scenarios
I have Picked the stressors I want to run regularly:
  - Network turbulence (packet loss, latency, jitter, reordering).
  - Resource pressure (CPU hog, memory leak, disk I/O contention).
  - Dependency faults (timeouts, 5xx errors, DNS failures).
  - Time skew (clock drift).
  - Randomized stressor mix (to simulate unpredictable failures).



  Adaptive Policies
  Implementing Adaptive fallbak chains into the AI agentvin a way that:
  - is explicit
  - updated the existing fallback metrics &
  - emits structured chaos / adaptation logs so Grafan + Loki can show when the agent degraded gracefully

1. Target behavior for the fallback chain
We’ll implement a simple, explicit chain:

Primary model – main LLM / toolflow

Secondary model – cheaper / smaller / more available model

Cached answer – last‑known‑good or heuristic default

Policy:

If primary fails or is low‑confidence → try secondary

If secondary fails or is low‑confidence → fall back to cached answer

Each step is logged as an adaptive action (adaptation_action="fallback")

Fallback metrics and antifragility metrics are updated




Adding Circuit Breakers and hedged requests
Circuit breakers + hedged requests turn your API into something that anticipates failure instead of merely responding to it.
Implementing a simple but production-grade circuit breaker with three states:
  CLOSED → normal operation
  OPEN → calls are blocked for a cooldown period
  HALF_OPEN → allow a single test request

HEDGED requests
Hedged requests reduce tail latency by sending a backup request if the first one is slow.
This is perfect for my chaos environment where latency spikes are injected.

This gives you:

automatic latency mitigation

structured logs for Grafana annotations

Prometheus metrics for hedged vs primary

chaos‑aware behavior (hedges fire more often during latency chaos)




- Using bandit algorithms for adaptive tool routing based o confidence and latency - This gives us 
online learning,continuous adaptation, and no retraining cycles. Perfect for a chaotic environment where latency
confidence and stressors flucuate.
My System currently has;
    - Primary model
    - Secondary model
    - Cached answer
We want the agent to learn over time which tool to route to, based on:
    - confidence
    - latency
    - success/failure
    - chaos conditions
    - fallback usage
Bandit algorithms are perfect because they:
    - exlore when uncertain
    - exploit when confident
    - adapt to changing conditions
    - dont require offline training
    - work in streaming environments

Given my metrics (confidence, latency, fallback events) the best choice is: UPPER CONFIDENCE COUND (UCB1)
Because:
It naturally balances exploration/exploitation
It handles non‑stationary environments (chaos)
It uses confidence intervals — perfect match for your LLM confidence
It’s simple and fast
We can later upgrade to
Thompson Sampling
Contextual Bandits (using CPU, memory, chaos stressor as context)
But UCB1 is the right starting point.


Adjusting cache TTLs dynamically when drift is detected 
- To make the cache self-tuning based on model drift.
- This is exactly how production-grade retrieval systems bahve: they shorten TTL when the world changes
quickly, and lengthen TTL when the environment is stable.

"Drift-aware TTL" meaning 
- The cache currently stores answers indefinitely (or with a fixed TTL)
But drift happens when:
  - model confidence Drops
  - answers change over time
  - chaos stressors distort outputs
  - bandit rewards degraded
  - fallback usage increases
  - latency spikes affect consistency
A static TTL cant handle that.
A dynamically TTL can.
The idea is simple:
  - High stability -> longer TTL
  - Detected drift -> shorter TTL
  - severe drift -> immediate invalidation
  





  Dashboard Queries in Grafana
  Query by stage in Grafana
  - Latency comparison - "histogram_quantile(0.95, sum(rate(resilient_latency_seconds_bucket[5m])) by (le, stage))
"
- Success rate: - "histogram_quantile(0.95, sum(rate(resilient_latency_seconds_bucket[5m])) by (le, stage))
"



13.53.193.146

Checking for routes
docker exec -it resilient-api flask routes
docker exec -it resilient-api flask --app app.py routes

docker exec -it resilient-api python -c "import learning; print(dir(learning))"

working - docker exec -it resilient-api python -m flask --app app.py routes



"""
while true; do
  stressor=$(shuf -e none timeout failure -n1)
  curl -s -X POST http://localhost:5002/resilient-api/process \
       -H "Content-Type: application/json" \
       -d "{\"value\": $RANDOM, \"stressor\": \"$stressor\"}" > /dev/null
  sleep 0.2
done



Intergrating Reinforcement learning Algorithm




When starting
Create a swap file to give the system breathing room
"""
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
"""

Pruning to save space
docker system prune -a --volumes -f

Retraining
Since prunning removed volumes, the saves resilience_agent.zip is gone. and we need to retrain
 docker compose run app python random_learning/train_rl.py