from __future__ import annotations

import time
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Response

from app.models.schemas import (
    CallEvent,
    DecisionResponse,
    RetellWebhookPayload,
)
from app.agents.orchestration_agent import OrchestrationAgent

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


app = FastAPI(
    title="Agentic Voice Telecom OS",
    version="0.1.0",
)

orchestrator = OrchestrationAgent()


# ============================================================
# METRICS
# ============================================================

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================
# WEBHOOK INGRESS (RETELL + STANDARD)
# ============================================================

@app.post("/call/event", response_model=DecisionResponse)
def handle_call_event(data: Dict[str, Any]):
    """
    Unified ingress point.

    Accepts:
    - Internal normalized CallEvent
    - Retell AI webhook payload via Make.com
    """

    try:
        # ----------------------------------------------------
        # CASE 1: Retell / Make webhook payload
        # ----------------------------------------------------
        if "event" in data and "call" in data:
            payload = RetellWebhookPayload(**data)

            if payload.call is None or payload.call.call_id is None:
                raise ValueError("Retell payload missing call_id")

            call = payload.call

            event = CallEvent(
                call_id=call.call_id,
                event_type=_map_retell_event(payload.event),
                error_reason=call.disconnect_reason,
                latency_ms=call.latency,
                timestamp=payload.timestamp or int(time.time()),
                rtp_loss=None,
                jitter=None,
            )

        # ----------------------------------------------------
        # CASE 2: Internal / Direct CallEvent
        # ----------------------------------------------------
        else:
            event = CallEvent(**data)

        decision = orchestrator.handle_event(event)
        return DecisionResponse(**decision)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Agentic OS internal error: {str(exc)}",
        )


# ============================================================
# HELPERS
# ============================================================

def _map_retell_event(retell_event: str) -> str:
    """
    Maps Retell event names to internal Agentic OS events.
    """

    mapping = {
        "call_started": "CALL_STARTED",
        "call_answered": "CALL_ANSWERED",
        "call_ended": "CALL_COMPLETED",
        "call_failed": "CALL_FAILED",
    }

    return mapping.get(retell_event.lower(), "CALL_FAILED")
