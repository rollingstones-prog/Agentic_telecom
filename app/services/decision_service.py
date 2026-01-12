# app/services/decision_service.py

from __future__ import annotations
from typing import Dict, Optional

from app.core.constants import (
    DECISION_RETRY,
    DECISION_STOP,
    DECISION_SUCCESS,
    DECISION_NO_ACTION,
    EVENT_CALL_FAILED,
    EVENT_CALL_COMPLETED,
)
from app.agents.healing_agent import HealingAgent
from app.agents.voice_quality_agent import VoiceQualityAgent


class DecisionService:
    """
    Production-grade Decision Coordinator
    """

    def __init__(self) -> None:
        self.healer = HealingAgent()
        self.vq = VoiceQualityAgent()

    def decide(
        self,
        *,
        call_id: str,
        event_type: str,
        current_state: str,
        retry_count: int,
        error_reason: Optional[str] = None,
        rtp_loss: Optional[float] = None,
        jitter: Optional[int] = None,
    ) -> Dict:
        """
        Returns FINAL agentic decision + metadata.
        """

        # 1. Voice Quality Scoring
        vq_payload = self.vq.score_quality(call_id, rtp_loss, jitter)
        
        # 2. Base Decision
        if event_type == EVENT_CALL_COMPLETED:
            return {
                "decision": DECISION_SUCCESS,
                "reason": "Success",
                "retry_count": retry_count,
                **vq_payload
            }

        # 3. Failure Handling (Healing)
        if event_type == EVENT_CALL_FAILED:
            # If RTP loss is high, override error reason
            if rtp_loss and rtp_loss > 10:
                error_reason = "RTP_LOSS_HIGH"

            healing_decision = self.healer.decide_healing(
                call_id=call_id,
                error_reason=error_reason,
                retry_count=retry_count,
            )

            return {
                "decision": healing_decision["decision"],
                "reason": healing_decision["reason"],
                "action": healing_decision.get("action"),
                "cooldown": healing_decision.get("cooldown"),
                "params": healing_decision.get("params", {}),
                "retry_count": retry_count,
                **vq_payload
            }

        # Default
        return {
            "decision": DECISION_NO_ACTION,
            "reason": None,
            "retry_count": retry_count,
            **vq_payload
        }
