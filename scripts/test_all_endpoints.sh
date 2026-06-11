#!/bin/bash

RESILIENT="http://localhost:5002"
FRAGILE="http://localhost:5003"
BASELINE="http://localhost:5004"
ADAPTIVE="http://localhost:5005"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

VALUES=(0 1 -1 1.5 10 -5 100 -100 0.001 7777777 42 -42 999 0.5 -0.5)
FUNCTION_TYPES=("data_processing" "llm_inference" "realtime_query")

print_result() {
    local name=$1
    local code=$2
    local body=$3
    local val=$4

    if [[ "$code" == "200" ]]; then
        echo -e "  ${GREEN}✓ [$code]${NC} value=$val → $(echo $body | python3 -m json.tool 2>/dev/null | grep -E 'result|answer|chosen_arm|stage' | head -3 | tr '\n' ' ')"
    elif [[ "$code" == "000" ]]; then
        echo -e "  ${RED}✗ [CONN]${NC} value=$val → connection refused"
    else
        echo -e "  ${RED}✗ [$code]${NC} value=$val → $(echo $body | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("error","unknown error"))' 2>/dev/null)"
    fi
}

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         ALL ENDPOINTS — MULTI VALUE TEST             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"

# -----------------------------------------------
# RESILIENT API
# -----------------------------------------------
echo ""
echo -e "${GREEN}━━━ RESILIENT API (port 5002) ━━━━━━━━━━━━━━━━━━━━━━━${NC}"
pass=0; fail=0
for val in "${VALUES[@]}"; do
    body=$(curl -s -w "\n%{http_code}" -X POST "$RESILIENT/resilient-api/process" \
        -H "Content-Type: application/json" \
        -d "{\"value\": $val}" --max-time 8)
    code=$(echo "$body" | tail -1)
    body=$(echo "$body" | head -1)
    print_result "Resilient" "$code" "$body" "$val"
    [[ "$code" == "200" ]] && ((pass++)) || ((fail++))
done
echo -e "  ${YELLOW}→ Results: ${GREEN}$pass passed${NC} / ${RED}$fail failed${NC} out of ${#VALUES[@]}"

# -----------------------------------------------
# FRAGILE API
# -----------------------------------------------
echo ""
echo -e "${RED}━━━ FRAGILE API (port 5003) ━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
pass=0; fail=0
for val in "${VALUES[@]}"; do
    body=$(curl -s -w "\n%{http_code}" -X POST "$FRAGILE/fragile-api/process" \
        -H "Content-Type: application/json" \
        -d "{\"value\": $val}" --max-time 10)
    code=$(echo "$body" | tail -1)
    body=$(echo "$body" | head -1)
    print_result "Fragile" "$code" "$body" "$val"
    [[ "$code" == "200" ]] && ((pass++)) || ((fail++))
done
echo -e "  ${YELLOW}→ Results: ${GREEN}$pass passed${NC} / ${RED}$fail failed${NC} out of ${#VALUES[@]}"

# -----------------------------------------------
# BASELINE API
# -----------------------------------------------
echo ""
echo -e "${YELLOW}━━━ BASELINE API (port 5004) ━━━━━━━━━━━━━━━━━━━━━━━${NC}"
pass=0; fail=0
for val in "${VALUES[@]}"; do
    body=$(curl -s -w "\n%{http_code}" -X POST "$BASELINE/baseline-api/process" \
        -H "Content-Type: application/json" \
        -d "{\"value\": $val}" --max-time 8)
    code=$(echo "$body" | tail -1)
    body=$(echo "$body" | head -1)
    print_result "Baseline" "$code" "$body" "$val"
    [[ "$code" == "200" ]] && ((pass++)) || ((fail++))
done
echo -e "  ${YELLOW}→ Results: ${GREEN}$pass passed${NC} / ${RED}$fail failed${NC} out of ${#VALUES[@]}"

# -----------------------------------------------
# ADAPTIVE API — all function types
# -----------------------------------------------
echo ""
echo -e "${BLUE}━━━ ADAPTIVE API (port 5005) ━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
for ft in "${FUNCTION_TYPES[@]}"; do
    echo -e "  ${CYAN}▸ function_type: $ft${NC}"
    pass=0; fail=0
    for val in "${VALUES[@]}"; do
        body=$(curl -s -w "\n%{http_code}" -X POST "$ADAPTIVE/adaptive-api/process" \
            -H "Content-Type: application/json" \
            -d "{\"value\": $val, \"function_type\": \"$ft\"}" --max-time 8)
        code=$(echo "$body" | tail -1)
        body=$(echo "$body" | head -1)
        print_result "Adaptive/$ft" "$code" "$body" "$val"
        [[ "$code" == "200" ]] && ((pass++)) || ((fail++))
    done
    echo -e "    ${YELLOW}→ $ft: ${GREEN}$pass passed${NC} / ${RED}$fail failed${NC}"
    echo ""
done

# Adaptive profile check
echo -e "  ${CYAN}▸ GET /adaptive-api/profile${NC}"
body=$(curl -s -w "\n%{http_code}" "$ADAPTIVE/adaptive-api/profile" --max-time 5)
code=$(echo "$body" | tail -1)
body=$(echo "$body" | head -1)
if [[ "$code" == "200" ]]; then
    echo -e "  ${GREEN}✓ [$code]${NC} profile → $(echo $body | python3 -m json.tool 2>/dev/null | head -5 | tr '\n' ' ')"
else
    echo -e "  ${RED}✗ [$code]${NC} profile check failed"
fi

# -----------------------------------------------
# SUMMARY
# -----------------------------------------------
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    SUMMARY                          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"

for endpoint in \
    "Resilient|$RESILIENT/resilient-api/process" \
    "Fragile|$FRAGILE/fragile-api/process" \
    "Baseline|$BASELINE/baseline-api/process"; do

    name=$(echo $endpoint | cut -d'|' -f1)
    url=$(echo $endpoint | cut -d'|' -f2)
    pass=0; fail=0
    for val in "${VALUES[@]}"; do
        code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "{\"value\": $val}" --max-time 8)
        [[ "$code" == "200" ]] && ((pass++)) || ((fail++))
    done
    total=$((pass + fail))
    pct=$((pass * 100 / total))
    bar=$(printf '█%.0s' $(seq 1 $((pct / 5))))
    echo -e "  $name: $bar ${pct}% ($pass/$total)"
done

echo ""
echo -e "  ${BLUE}Adaptive: check per function type above${NC}"
echo -e "  ${CYAN}Grafana dashboard → http://localhost:3001${NC}"
echo ""
