# chaos/strategy_map.py
from resilient_api.app import get_answer_with_fallback_chain, hedged_request, resilient_operation

def execute_strategy(arm, value, sys_metrics):
    if arm == "fallback_chain":
        return get_answer_with_fallback_chain(str(value), sys_metrics)

    elif arm == "circuit_breaker":
        return resilient_operation(value, stressor="none")

    elif arm == "hedged_request":
        return hedged_request(lambda: get_answer_with_fallback_chain(str(value), sys_metrics), timeout=0.25)

    else:
        raise ValueError(f"Unknown arm: {arm}")
