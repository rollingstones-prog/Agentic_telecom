from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ============================================================
# 1️⃣ EXTERNAL PAYLOAD (RETELL / MAKE WEBHOOK)
# ============================================================

class RetellCall(BaseModel):
    """
    Raw call object received from Retell via Make.com webhook.
    VERY LOOSE schema by design.
    Retell sends partial data depending on event type.
    """

    # 🔑 CRITICAL IDENTIFIER
    call_id: Optional[str] = None

    call_status: Optional[str] = None
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    duration_ms: Optional[int] = None
    latency: Optional[int] = None

    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None

    call_cost: Optional[float] = None

    transcript: Optional[str] = None
    transcript_object: Optional[List[Dict[str, Any]]] = None

    recording_url: Optional[str] = None
    public_log_url: Optional[str] = None

    disconnect_reason: Optional[str] = None


class RetellWebhookPayload(BaseModel):
    """
    Full webhook payload received from Make.com (origin: Retell).
    EXTREMELY LOOSE — never trust external systems.
    """

    event: str
    timestamp: Optional[int] = None
    call: Optional[RetellCall] = None


# ============================================================
# 2️⃣ INTERNAL NORMALIZED EVENT (AGENTIC OS TRUST BOUNDARY)
# ============================================================

class CallEvent(BaseModel):
    """
    Internal normalized event.
    This is the ONLY thing the Agentic OS trusts.
    """

    call_id: str = Field(
        ...,
        description="Globally unique call identifier",
        min_length=1,
    )

    event_type: str = Field(
        ...,
        description="CALL_STARTED | CALL_ANSWERED | CALL_FAILED | CALL_COMPLETED",
        min_length=1,
    )

    error_reason: Optional[str] = Field(
        default=None,
        description="NO_ANSWER | BUSY | SIP_TIMEOUT | AUDIO_LOSS | UNKNOWN",
    )

    latency_ms: Optional[int] = Field(
        default=None,
        description="End-to-end call latency in milliseconds",
        ge=0,
    )

    timestamp: Optional[int] = Field(
        default=None,
        description="Unix timestamp (seconds)",
        ge=0,
    )

    # Voice quality signals (future-ready)
    rtp_loss: Optional[float] = Field(
        default=None,
        description="RTP packet loss percentage",
    )

    jitter: Optional[int] = Field(
        default=None,
        description="Jitter in milliseconds",
    )


# ============================================================
# 3️⃣ AGENTIC DECISION RESPONSE (PURE, SIDE-EFFECT FREE)
# ============================================================

class DecisionResponse(BaseModel):
    """
    Pure agentic decision.
    NO execution. NO SIP. NO Retell logic.
    """

    call_id: str

    decision: str = Field(
        ...,
        description="RETRY | STOP | SUCCESS | NO_ACTION",
    )

    reason: Optional[str] = Field(
        default=None,
        description="Why this decision was made",
    )

    retry_count: Optional[int] = Field(
        default=None,
        description="Retry count after this decision",
        ge=0,
    )

    current_state: Optional[str] = Field(
        default=None,
        description="Current call lifecycle state",
    )

    # Deterministic action layer
    action: Optional[str] = Field(
        default=None,
        description="Deterministic action to take",
    )

    cooldown: Optional[int] = Field(
        default=None,
        description="Cooldown time in seconds",
    )

    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional action parameters",
    )

    # Observability & SLA
    voice_quality: Optional[str] = Field(
        default=None,
        description="OK | POOR",
    )

    score: Optional[float] = Field(
        default=None,
        description="Quality score (0.0 to 1.0)",
    )

    sla_status: Optional[str] = Field(
        default=None,
        description="SLA_OK | SLA_BREACH",
    )

    violations: Optional[List[str]] = Field(
        default_factory=list,
        description="List of SLA violations",
    )


# ============================================================
# 4️⃣ MODEL REBUILD (SAFE GUARD)
# ============================================================

DecisionResponse.model_rebuild()
