# app/agents/healing_agent.py

from __future__ import annotations
from typing import Dict, Optional


class HealingAgent:
    """
    Production-grade Healing Agent

    Responsibilities:
    - Decide recovery action based on error type + retry count
    - NO execution
    - NO Redis
    - NO SIP / Retell logic
    """

    # 🔒 Day-3 Telecom healing policy matrix
    HEALING_POLICY = {
        "NO_ANSWER": {
            "max": 2,
            "retry": True,
            "action": "RETRY_CALL",
            "cooldown": 30,
            "reason": "No response",
        },
        "BUSY": {
            "max": 0,
            "retry": False,
            "action": "ESCALATE_TO_SMS",
            "cooldown": 0,
            "reason": "Target busy",
        },
        "SIP_TIMEOUT": {
            "max": 3,
            "retry": True,
            "action": "REINVITE",
            "cooldown": 10,
            "reason": "Timeout",
        },
        "AUDIO_LOSS": {
            "max": 1,
            "retry": True,
            "action": "SWITCH_CODEC",
            "cooldown": 0,
            "reason": "Audio issue",
        },
        "RTP_LOSS_HIGH": {
            "max": 1,
            "retry": True,
            "action": "SWITCH_CODEC",
            "cooldown": 0,
            "reason": "Poor quality network",
        },
        "DEFAULT": {
            "max": 0,
            "retry": False,
            "action": "LOG_AND_STOP",
            "cooldown": 0,
            "reason": "Unknown",
        },
    }

    def decide_healing(
        self,
        call_id: str,
        error_reason: Optional[str],
        retry_count: int,
    ) -> Dict:
        """
        Decide what to do AFTER a failure.
        Updates shared context for team awareness.
        """
        from app.services.redis_service import RedisService
        redis = RedisService()

        # Normalize error
        error = (error_reason or "DEFAULT").upper()

        policy = self.HEALING_POLICY.get(
            error,
            self.HEALING_POLICY["DEFAULT"],
        )

        max_retries = policy["max"]
        can_retry = policy["retry"]
        
        retries_exceeded = retry_count >= max_retries

        # 🔴 Retry limit reached or not allowed
        if not can_retry or retries_exceeded:
            decision = {
                "decision": "STOP",
                "action": policy["action"],
                "reason": f"{policy['reason']} (LIMIT_REACHED)" if retries_exceeded else policy["reason"],
                "cooldown": policy["cooldown"],
                "params": {},
            }
        else:
            # 🟢 Retry allowed
            decision = {
                "decision": "RETRY",
                "action": policy["action"],
                "reason": policy["reason"],
                "cooldown": policy["cooldown"],
                "params": {},
            }

        # Update shared state
        redis.update_team_state(call_id, {
            "error_code": error,
            "retry_count": retry_count,
            "retries_exceeded": retries_exceeded,
            "last_action": decision["action"]
        })

        return decision
