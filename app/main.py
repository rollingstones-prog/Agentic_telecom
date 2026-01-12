# app/main.py

from __future__ import annotations
import time

from fastapi import FastAPI, HTTPException

from app.models.schemas import CallEvent, DecisionResponse
from app.agents.orchestration_agent import OrchestrationAgent
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

app = FastAPI(
    title="Agentic Voice Telecom OS",
    version="0.1.0",
)

orchestrator = OrchestrationAgent()

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/call/event", response_model=DecisionResponse)
def handle_call_event(data: dict):
    """
    Hybrid ingress point. 
    Accepts both standard CallEvent and Retell AI webhooks.
    """
    try:
        # Retell AI Adapter: Detect if this is a Retell payload
        if "call" in data and "call_id" in data["call"]:
            retell_call = data["call"]
            event = CallEvent(
                call_id=retell_call["call_id"],
                event_type="CALL_FAILED" if retell_call.get("disconnection_reason") in ["error", "machine_detected"] else "CALL_COMPLETED",
                error_reason=retell_call.get("disconnection_reason"),
                rtp_loss=0.0,
                jitter=0
            )
        else:
            # Standard format
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
