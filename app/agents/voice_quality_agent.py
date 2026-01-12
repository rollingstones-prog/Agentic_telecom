# app/agents/voice_quality_agent.py

from __future__ import annotations
from typing import Dict, Optional
from app.core.constants import QUALITY_OK, QUALITY_POOR

class VoiceQualityAgent:
    """
    Agent #3: Voice Quality Agent
    
    Responsibilities:
    - Score call quality using deterministic thresholds.
    - RTP loss > 5% -> POOR
    - Jitter > 30 ms -> POOR
    """

    def score_quality(self, call_id: str, rtp_loss: Optional[float], jitter: Optional[int]) -> Dict:
        """
        Input: { "call_id": str, "rtp_loss": float, "jitter": int }
        Output: { "voice_quality": "OK" | "POOR", "score": float }
        """
        from app.services.redis_service import RedisService
        redis = RedisService()
        
        rtp_loss = rtp_loss or 0.0
        jitter = jitter or 0
        
        # 1.0 is perfect, 0.0 is silent/failed
        base_score = 1.0
        
        # Penalty for loss
        loss_penalty = min(rtp_loss * 0.1, 0.5)
        
        # Penalty for jitter
        jitter_penalty = min((jitter / 100.0) * 0.2, 0.3)
        
        score = max(0.0, base_score - loss_penalty - jitter_penalty)
        score = round(score, 2)
        
        is_poor = rtp_loss > 5 or jitter > 30
        
        quality_data = {
            "voice_quality": QUALITY_POOR if is_poor else QUALITY_OK,
            "score": score
        }
        
        # Update shared state
        redis.update_team_state(call_id, {
            "rtp_loss": rtp_loss,
            "jitter": jitter,
            "quality_score": score,
            "voice_quality": quality_data["voice_quality"]
        })
        
        return quality_data
