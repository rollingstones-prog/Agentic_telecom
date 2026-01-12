from __future__ import annotations
from typing import Dict, Any, Literal, Optional
from pydantic import BaseModel
from app.services.redis_service import RedisService
import time
from prometheus_client import Gauge

# NOTE: LangGraph is the backbone of this deterministic collaboration
# In a real PROD env, you would run 'pip install langgraph'
try:
    from langgraph.graph import StateGraph, END, START
except ImportError:
    # Minimal mock for graph-less testing if needed
    START = "__start__"
    class END: pass
    class StateGraph:
        def __init__(self, *args, **kwargs): pass
        def add_node(self, *args, **kwargs): pass
        def add_edge(self, *args, **kwargs): pass
        def add_conditional_edges(self, *args, **kwargs): pass

try:
    from crewai import Agent, Task, Crew, Process
    # Check if we need to wrap Anthropic for CrewAI
    # In newer CrewAI, we pass llm object.
    from langchain_anthropic import ChatAnthropic
except ImportError:
    class Agent: pass
    class Task: pass
    class Crew: pass
    class Process: pass
    class ChatAnthropic: pass

try:
    from replit.ai.modelfarm import ChatModel, ChatSession
except ImportError:
    class ChatModel: pass
    class ChatSession: pass

from app.core.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_NAME, REPLIT_API_KEY

class TeamState(BaseModel):
    call_id: str
    context: Dict[str, Any]  # Shared context bag (e.g., error_code, load_level)
    current_task: Literal["ORCHESTRATE", "LOAD_CHECK", "QUALITY_ASSESS", "HEAL_DECIDE", "SLA_MONITOR", "ESCALATE", "CREW_ROUTING"]
    decision: Dict[str, Any] = {}

# Prometheus Metrics
decision_latency = Gauge('decision_latency_seconds', 'Agent decision time', ['agent_type'])
fallback_usage = Gauge('fallback_usage_count', 'Replit fallback activations')

class SupervisorAgent:
    """
    Supervisor Agent (Agent #9): The Central Router
    
    Responsibilities:
    - Analyzes shared context to route to specialized agents.
    - No direct execution; only control flow.
    """

    def __init__(self):
        self.redis = RedisService()
        self._init_crew()

    def _init_crew(self):
        """Setup CrewAI for heavy orchestration decisions."""
        if not ANTHROPIC_API_KEY:
            self.master_crew = None
            return

        llm = ChatAnthropic(
            model=ANTHROPIC_MODEL_NAME,
            anthropic_api_key=ANTHROPIC_API_KEY
        )

        # Define Agents
        self.orchestrator = Agent(
            role='Telecom Orchestrator',
            goal='Decide the best next step for a call based on context.',
            backstory='Expert in SIP protocol and system health. You prioritize stability.',
            verbose=True,
            llm=llm
        )

        self.quality_analyst = Agent(
            role='Quality Analyst',
            goal='Identify voice quality issues and suggest remedies.',
            backstory='Specialist in RTP jitter, packet loss, and codec switching.',
            verbose=True,
            llm=llm
        )

        self.healing_expert = Agent(
            role='Self-Healing Specialist',
            goal='Determine if a failed call can be recovered.',
            backstory='Expert in retry policies and edge case recovery.',
            verbose=True,
            llm=llm
        )

        # We will use this crew dynamically in the supervisor
        self.master_crew = None # Initialized on demand with specific task

    def crewai_supervisor(self, state: TeamState) -> TeamState:
        """
        Uses CrewAI to make a high-level orchestration decision.
        """
        if not self.orchestrator or not ANTHROPIC_API_KEY:
            # Fallback to deterministic logic if no LLM
            state.decision["action"] = "FALLBACK_DETERMINISTIC"
            return state

        ctx = state.context
        
        routing_task = Task(
            description=f"Analyze context: {ctx}. Decide which agent to call next. Options: load_agent, voice_quality_agent, self_healing_agent, orchestration_agent, sla_agent.",
            agent=self.orchestrator,
            expected_output="A single word from the options provided."
        )

        crew = Crew(
            agents=[self.orchestrator, self.quality_analyst, self.healing_expert],
            tasks=[routing_task],
            process=Process.sequential,
            verbose=True
        )

        try:
            start_time = time.time()
            result = crew.kickoff()
            latency = time.time() - start_time
            decision_latency.labels(agent_type='crewai').set(latency)

            # Parse result and update state
            route = str(result).strip().lower()
            state.decision["crewai_route"] = route
            self.redis.update_team_state(state.call_id, {"crewai_decision": route})
        except Exception as e:
            print(f"CrewAI Master Failed: {e}")
            state.context["crewai_failed"] = True
            state.decision["crewai_status"] = "FAILED"
        
        return state

    def replit_fallback(self, state: TeamState) -> TeamState:
        """
        Cost-optimized fallback using Replit's AI model.
        Triggered on CrewAI failure or high cost threshold.
        """
        ctx = state.context
        if not REPLIT_API_KEY:
            # SIMULATED FALLBACK for testing if key is missing
            route = "self_healing_agent" if ctx.get("error_code") else "orchestration_agent"
            state.decision["crewai_route"] = route
            state.decision["fallback_used"] = "SIMULATED"
            self.redis.update_team_state(state.call_id, {"fallback_used": True, "simulated": True, "replit_decision": route})
            return state

        try:
            start_time = time.time()
            model = ChatModel('chat-bison') # Or other Replit model
            session = ChatSession(model=model)
            prompt = f"Route context: {ctx}; decide next agent from [load_agent, voice_quality_agent, self_healing_agent, orchestration_agent, sla_agent]."
            response = session.reply(prompt)
            
            latency = time.time() - start_time
            decision_latency.labels(agent_type='replit').set(latency)
            fallback_usage.inc()

            route = str(response.text).strip().lower()
            state.decision["crewai_route"] = route # Reuse same slot for simplicity
            self.redis.update_team_state(state.call_id, {"fallback_used": True, "replit_decision": route})
        except Exception as e:
            print(f"Replit Fallback Failed: {e}")
            state.decision["fallback_used"] = "FAILED"

        return state

    def supervisor_router(self, state: TeamState) -> str:
        """
        Determines the next best agent based on shared context.
        Returns the name of the next node to execute.
        """
        ctx = state.context
        
        # 0. Edge Cases (Emergency Abort)
        if ctx.get("concurrent_failures", 0) > 5:
            return "edge_handler"

        # If CrewAI made a decision, use it (or use it as primary)
        if state.decision.get("crewai_route"):
            route = state.decision["crewai_route"]
            if "load" in route: return "load_agent"
            if "quality" in route: return "voice_quality_agent"
            if "heal" in route: return "self_healing_agent"
            if "sla" in route: return "sla_agent"
            return "orchestration_agent"

        # Default Deterministic Logic (Fallback)
        if ctx.get("active_calls", 0) > ctx.get("concurrency_limit", 10):
            return "load_agent"
        if ctx.get("rtp_loss", 0) > 5 or ctx.get("jitter", 0) > 30:
            return "voice_quality_agent"
        if ctx.get("error_code") in ["NO_ANSWER", "408", "503", "BUSY", "SIP_TIMEOUT", "AUDIO_LOSS"]:
            return "self_healing_agent"
        if ctx.get("sla_breach_flagged"):
            return "sla_agent"

        return "orchestration_agent"

    def handle_edge_cases(self, state: TeamState) -> TeamState:
        """
        Hardening: Simultaneous failure threshold.
        """
        ctx = state.context
        if ctx.get('concurrent_failures', 0) > 5:
            state.decision.update({
                "action": "GLOBAL_ABORT", 
                "reason": "System overload: high concurrent failures"
            })
            self.redis.update_team_state(state.call_id, {"aborted": True})
        return state

    def build_graph(self):
        """
        Initializes the LangGraph for the team.
        """
        workflow = StateGraph(TeamState)
        
        workflow.add_node("crewai_master", self.crewai_supervisor)
        workflow.add_node("replit_fallback", self.replit_fallback)
        workflow.add_node("supervisor", self.supervisor_router)
        workflow.add_node("edge_handler", self.handle_edge_cases)
        
        # Entry
        workflow.add_edge(START, "crewai_master")
        
        # Fallback Logic: If CrewAI fails or cost high, go Replit
        workflow.add_conditional_edges(
            "crewai_master",
            lambda s: "replit_fallback" if s.context.get('cost_high') or s.context.get('crewai_failed') or not ANTHROPIC_API_KEY else "supervisor"
        )
        
        workflow.add_edge("replit_fallback", "supervisor")
        workflow.add_conditional_edges("supervisor", self.supervisor_router)
        
        return workflow

    def get_shared_context(self, call_id: str) -> Dict[str, Any]:
        """Fetch historical context from Redis for routing."""
        return self.redis.get_team_state(call_id)
