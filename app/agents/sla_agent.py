# app/agents/sla_agent.py

from __future__ import annotations
from typing import Dict

from app.services.redis_service import RedisService


class SLAAgent:
    """
    SLA & Monitoring Agent
    READ-ONLY observer
    Redis-safe
    """

    # SLA Policies
    SLA_CONFIG = {
        "call_success_rate": {"threshold": 0.97, "window": 3600},
        "recovery_time_sec": {"threshold": 5.0, "window": 3600},
    }

    def __init__(self) -> None:
        self.redis = RedisService()

    def record_event(self, *, event_type: str, success: bool, recovery_time: Optional[float] = None) -> Dict:
        """
        Record event for SLA tracking.
        """
        # Record success/failure
        self.redis.record_sla_metric(
            metric_name="success_rate",
            value="1" if success else "0",
            window_seconds=3600
        )
        
        # Record recovery time if applicable
        if recovery_time is not None:
            self.redis.record_sla_metric(
                metric_name="recovery_time",
                value=str(recovery_time),
                window_seconds=3600
            )
            
        return self.check_sla_status()

    def check_sla_status(self) -> Dict:
        """
        Detect SLA breaches based on sliding windows.
        """
        violations = []
        
        # 1. Success Rate Check
        success_events = self.redis.get_sla_metrics(metric_name="success_rate", window_seconds=3600)
        if success_events:
            success_count = sum(1 for e in success_events if e == "1")
            total = len(success_events)
            rate = success_count / total
            if rate < self.SLA_CONFIG["call_success_rate"]["threshold"]:
                violations.append("LOW_SUCCESS_RATE")
        
        # 2. Recovery Time Check
        recovery_events = self.redis.get_sla_metrics(metric_name="recovery_time", window_seconds=3600)
        if recovery_events:
            avg_recovery = sum(float(e) for e in recovery_events) / len(recovery_events)
            if avg_recovery > self.SLA_CONFIG["recovery_time_sec"]["threshold"]:
                violations.append("SLOW_RECOVERY")

        status = "BREACH" if violations else "SLA_OK"
        
        return {
            "sla_status": status,
            "violations": violations
        }
