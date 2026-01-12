# app/agents/orchestration_agent.py

from __future__ import annotations
from typing import Dict
import time

from app.core.constants import (
    EVENT_CALL_STARTED,
    EVENT_CALL_ANSWERED,
    EVENT_CALL_FAILED,
    EVENT_CALL_COMPLETED,
    EVENT_TO_STATE,
    STATE_COMPLETED,
)
from app.models.schemas import CallEvent
from app.services.redis_service import RedisService
from app.services.decision_service import DecisionService
from app.agents.sla_agent import SLAAgent
from app.agents.load_agent import LoadAgent
from app.agents.supervisor_agent import SupervisorAgent, TeamState
from app.agents.team_workflow import TeamWorkflow


class OrchestrationAgent:
    """
    Production-grade Call Orchestration Agent

    Responsibilities:
    - Single source of truth for call lifecycle
    - Deterministic retry handling
    - No execution logic
    - No SIP / Retell coupling
    """

    def __init__(self) -> None:
        self.redis = RedisService()
        self.decider = DecisionService()
        self.sla = SLAAgent()
        self.load = LoadAgent()
        self.supervisor = SupervisorAgent()
        self.workflow = TeamWorkflow()


    def handle_event(self, event: CallEvent) -> Dict:
        """
        Main orchestration entrypoint.
        This method is SIDE-EFFECT SAFE and AUDITABLE.
        """

        # 1. Initialize Shared State (Team Layer)
        self.redis.update_team_state(event.call_id, {
            "current_task": "ORCHESTRATE",
            "event_type": event.event_type
        })

        # 2. Load Check (Pre-orchestration for new calls)
        if event.event_type == EVENT_CALL_STARTED:
            load_decision = self.load.evaluate_load(event.call_id)
            if load_decision["decision"] != "ALLOW_CALL":
                # Team routing for load rejection
                state = TeamState(
                    call_id=event.call_id,
                    context=self.redis.get_team_state(event.call_id),
                    current_task="LOAD_CHECK"
                )
                team_decision = self.workflow.handle_load_rejection(state)
                return {
                    "call_id": event.call_id,
                    **team_decision.decision,
                    "retry_count": 0,
                    "current_state": "LOAD_REJECTED",
                }

        # 2. State Lookup
        state_data = self.redis.initialize_call_if_missing(event.call_id)
        current_state = state_data.get("state")
        retry_count = int(state_data.get("retry_count", 0))

        # 3. State Mapping
        next_state = EVENT_TO_STATE.get(event.event_type)
        if next_state is None:
            return {
                "call_id": event.call_id,
                "decision": "NO_ACTION",
                "reason": "UNKNOWN_EVENT",
            }

        # 4. Terminal Protection
        if current_state == STATE_COMPLETED:
            return {
                "call_id": event.call_id,
                "decision": "NO_ACTION",
                "reason": "ALREADY_COMPLETED",
            }

        # 6. DECISION PHASE (Enhanced with shared context)
        decision_payload = self.decider.decide(
            call_id=event.call_id,
            event_type=event.event_type,
            current_state=current_state,
            retry_count=retry_count,
            error_reason=event.error_reason,
            rtp_loss=event.rtp_loss,
            jitter=event.jitter,
        )

        # 7. TEAM COLLABORATION: Supervisor Routing
        shared_ctx = self.redis.get_team_state(event.call_id)
        team_state = TeamState(
            call_id=event.call_id,
            context=shared_ctx,
            current_task="ORCHESTRATE",
            decision=decision_payload
        )
        
        # Check for potential escalations before final response
        if decision_payload.get("decision") == "STOP" and shared_ctx.get("retries_exceeded"):
            team_state = self.workflow.handle_escalation(team_state)
            decision_payload = team_state.decision

        decision = decision_payload["decision"]
        
        # 6. Apply Side Effects
        if event.event_type == EVENT_CALL_FAILED and decision == "RETRY":
            retry_count = self.redis.increment_retry(event.call_id)

        # 7. Update State
        self.redis.update_call_state(event.call_id, state=next_state)

        # 8. SLA & Load Release
        sla_status = {"sla_status": "SLA_OK", "violations": []}
        
        if event.event_type == EVENT_CALL_COMPLETED:
            self.load.release_load()
            sla_status = self.sla.record_event(event_type=event.event_type, success=True)
        elif event.event_type == EVENT_CALL_FAILED:
            self.load.release_load()
            sla_status = self.sla.record_event(
                event_type=event.event_type, 
                success=False,
                recovery_time=decision_payload.get("cooldown", 0) if decision == "RETRY" else None
            )

        # 9. FINAL RESPONSE
        return {
            "call_id": event.call_id,
            "decision": decision,
            "reason": decision_payload.get("reason"),
            "action": decision_payload.get("action"),
            "cooldown": decision_payload.get("cooldown"),
            "params": decision_payload.get("params", {}),
            "retry_count": retry_count,
            "current_state": next_state,
            "voice_quality": decision_payload.get("voice_quality"),
            "score": decision_payload.get("score"),
            **sla_status
        }
