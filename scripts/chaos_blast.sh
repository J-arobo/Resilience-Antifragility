#!/bin/bash

RESILIENT="http://localhost:5002"
FRAGILE="http://localhost:5003"
BASELINE="http://localhost:5004"
ADAPTIVE="http://localhost:5005"

VALUES=(10 0 -5 1.5 7777777 100 -100 0.001 999)
FUNCTION_TYPES=("data_processing" "llm_inference" "realtime_query")

echo "======================================"
echo " CHAOS BLAST — hitting all endpoints"
echo "======================================"

send_requests() {
    local label=$1
    local url=$2
    local payload=$3
    local count=$4

    success=0
    fail=0
    for i in $(seq 1 $count); do
        code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$payload" \
            --max-time 5)
        if [[ "$code" == "200" ]]; then
            ((success++))
        else
            ((fail++))
        fi
    done
    echo "[$label] sent=$count success=$success fail=$fail"
}

# -----------------------------------------------
# Round 1 — baseline load, no chaos
# -----------------------------------------------
echo ""
echo "--- Round 1: Baseline load (no chaos) ---"

for val in "${VALUES[@]}"; do
    payload="{\"value\": $val}"

    curl -s -o /dev/null -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" -d "$payload" &

    for ft in "${FUNCTION_TYPES[@]}"; do
        curl -s -o /dev/null -X POST "$ADAPTIVE/adaptive-api/process" \
            -H "Content-Type: application/json" \
            -d "{\"value\": $val, \"function_type\": \"$ft\"}" &
    done
done
wait
echo "Round 1 done."

# -----------------------------------------------
# Round 2 — inject CPU chaos, keep sending
# -----------------------------------------------
echo ""
echo "--- Round 2: CPU chaos (2 cores, 45s) ---"
curl -s -X POST "$RESILIENT/chaos/cpu" \
    -H "Content-Type: application/json" \
    -d '{"cores": 2, "seconds": 45}' &

for i in $(seq 1 20); do
    val=${VALUES[$((RANDOM % ${#VALUES[@]}))]}
    payload="{\"value\": $val}"
    curl -s -o /dev/null -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    sleep 0.3
done
wait
echo "Round 2 done."

# -----------------------------------------------
# Round 3 — network chaos + requests
# -----------------------------------------------
echo ""
echo "--- Round 3: Network chaos (loss=20%, delay=200ms) ---"
curl -s -X POST "$RESILIENT/chaos/network" \
    -H "Content-Type: application/json" \
    -d '{"loss": 20, "delay_ms": 200, "jitter_ms": 50}'

for i in $(seq 1 20); do
    val=${VALUES[$((RANDOM % ${#VALUES[@]}))]}
    payload="{\"value\": $val}"
    curl -s -o /dev/null -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    ft=${FUNCTION_TYPES[$((RANDOM % 3))]}
    curl -s -o /dev/null -X POST "$ADAPTIVE/adaptive-api/process" \
        -H "Content-Type: application/json" \
        -d "{\"value\": $val, \"function_type\": \"$ft\"}" &
    sleep 0.2
done
wait
echo "Round 3 done."

# -----------------------------------------------
# Round 4 — memory pressure
# -----------------------------------------------
echo ""
echo "--- Round 4: Memory pressure (80MB, 60s) ---"
curl -s -X POST "$RESILIENT/chaos/memory" \
    -H "Content-Type: application/json" \
    -d '{"mb": 80, "seconds": 60}'

for i in $(seq 1 15); do
    val=${VALUES[$((RANDOM % ${#VALUES[@]}))]}
    payload="{\"value\": $val}"
    curl -s -o /dev/null -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    sleep 0.3
done
wait
echo "Round 4 done."

# -----------------------------------------------
# Round 5 — combined CPU + network + memory
# -----------------------------------------------
echo ""
echo "--- Round 5: COMBINED chaos (CPU + network + memory) ---"
curl -s -X POST "$RESILIENT/chaos/cpu" \
    -H "Content-Type: application/json" \
    -d '{"cores": 2, "seconds": 60}' &
curl -s -X POST "$RESILIENT/chaos/network" \
    -H "Content-Type: application/json" \
    -d '{"loss": 30, "delay_ms": 300, "jitter_ms": 100}'
curl -s -X POST "$RESILIENT/chaos/memory" \
    -H "Content-Type: application/json" \
    -d '{"mb": 64, "seconds": 60}'

echo "All chaos active — hammering all endpoints for 30s..."
end=$((SECONDS + 30))
while [ $SECONDS -lt $end ]; do
    val=${VALUES[$((RANDOM % ${#VALUES[@]}))]}
    payload="{\"value\": $val}"
    curl -s -o /dev/null -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    curl -s -o /dev/null -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" -d "$payload" &
    ft=${FUNCTION_TYPES[$((RANDOM % 3))]}
    curl -s -o /dev/null -X POST "$ADAPTIVE/adaptive-api/process" \
        -H "Content-Type: application/json" \
        -d "{\"value\": $val, \"function_type\": \"$ft\"}" &
    sleep 0.15
done
wait
echo "Round 5 done."

# -----------------------------------------------
# Reset all chaos
# -----------------------------------------------
echo ""
echo "--- Resetting all chaos ---"
curl -s -X POST "$RESILIENT/chaos/reset"
echo ""
echo "======================================"
echo " BLAST COMPLETE — check Grafana"
echo " http://localhost:3001"
echo "======================================"
