# app/agents/load_agent.py

from __future__ import annotations
from typing import Dict
from app.services.redis_service import RedisService, MemoryRedis
from app.core.constants import DECISION_ALLOW_CALL, DECISION_DELAY, DECISION_REJECT, LOAD_REASON_HIGH_LOAD

# Note: DECISION_ALLOW_CALL etc might missing from constants, I should check or use strings
# I added DECISION_DELAY and DECISION_REJECT to constants. 
# Let's use strings or ensure they are imported.
# I'll use strings to be safe or add them if not there. 
# Wait, I added them in Step 53.

class LoadAgent:
    """
    Agent #5: Load & Channel Agent
    
    Responsibilities:
    - Prevent overload and unsafe concurrency.
    - Semaphore-style decisions.
    """

    def __init__(self) -> None:
        self.redis = RedisService()
        self.max_concurrency = 100 # Example threshold

    def evaluate_load(self, call_id: str) -> Dict:
        """
        Stateless load decision with shared state update.
        """
        allowed = self.redis.check_load_concurrency(self.max_concurrency)
        
        decision_data = {
            "decision": "ALLOW_CALL" if allowed else "DELAY",
            "reason": "OK" if allowed else "HIGH_LOAD"
        }
        
        # Update shared state
        self.redis.update_team_state(call_id, {
            "active_calls": int(self.redis.client.get("load:active_calls") or 0) if not isinstance(self.redis.client, MemoryRedis) else int(self.redis.client._data.get("load:active_calls", {}).get("count", 0)),
            "concurrency_limit": self.max_concurrency,
            "load_level": "OVERLOAD" if not allowed else "NORMAL"
        })
        
        return decision_data

    def release_load(self) -> None:
        self.redis.release_load_concurrency()
