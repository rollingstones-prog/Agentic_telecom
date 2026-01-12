import sys
import os
import json
import time

# Add project root to path
sys.path.append(os.getcwd())

from app.agents.supervisor_agent import SupervisorAgent, TeamState
from app.services.redis_service import RedisService

def run_final_suite():
    print("\n" + "="*50)
    print("FINAL TEST SUITE: CREWAI + REPLIT FALLBACK")
    print("="*50)

    sup = SupervisorAgent()
    redis = RedisService()

    scenarios = [
        {
            "id": "c_crew_1",
            "desc": "CrewAI Routing (Poor Quality -> Voice Agent)",
            "context": {"rtp_loss": 12.0, "jitter": 45}
        },
        {
            "id": "c_fallback_1",
            "desc": "Replit Fallback (High Cost Trigger)",
            "context": {"error_code": "NO_ANSWER", "cost_high": True}
        },
        {
            "id": "c_abort_1",
            "desc": "Deterministic Edge Case (Global Abort)",
            "context": {"concurrent_failures": 10}
        }
    ]

    for sc in scenarios:
        print(f"\n[Scenario]: {sc['desc']}")
        call_id = sc["id"]
        
        # Initialize state in Redis
        redis.update_team_state(call_id, sc["context"])
        
        # Prepare state for LangGraph
        state = TeamState(
            call_id=call_id,
            context=sc["context"],
            current_task="CREW_ROUTING"
        )
        
        # Step 1: Master Decision (CrewAI or Replit)
        try:
            if sc["context"].get("cost_high"):
                print("Running Replit Fallback...")
                state = sup.replit_fallback(state)
            else:
                print("Running CrewAI Primary...")
                # Note: CrewAI might fail if no valid API key or net issues.
                # In simulation/local env, it might fallback to deterministic if keys are missing.
                state = sup.crewai_supervisor(state)
        except Exception as e:
            print(f"Master Logic Error: {e}")

        # Step 2: Routing Decision
        next_node = sup.supervisor_router(state)
        
        # Audit results
        final_state = redis.get_team_state(call_id)
        print(f"Routing Decision: {next_node}")
        print(f"Audit Trail Status: {'fallback_used' in final_state}")
        # print(f"Audit Trail: {json.dumps(final_state, indent=2)}")

        # Verification
        if sc["id"] == "c_abort_1":
            success = next_node == "edge_handler"
        elif sc["id"] == "c_crew_1":
            # CrewAI might be smart enough to route to voice_quality_agent
            success = "quality" in str(state.decision.get("crewai_route", "")) or next_node == "voice_quality_agent"
        elif sc["id"] == "c_fallback_1":
            success = final_state.get("fallback_used") == True or state.decision.get("fallback_used") == "SIMULATED"
        else:
            success = True

        status = "PASS" if success else "FAIL"
        print(f"Result: {status}")

    print("\n" + "="*50)
    print("FINAL SUITE COMPLETE")
    print("="*50 + "\n")

if __name__ == "__main__":
    # Ensure .env is loaded (handled in config, but good to be sure)
    from dotenv import load_dotenv
    load_dotenv()
    run_final_suite()
