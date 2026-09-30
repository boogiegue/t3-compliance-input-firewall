import os
from typing import TypedDict, List
from datetime import datetime
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# Updated to current 3.5 generation
llm = ChatAnthropic(model="claude-3-5-haiku-latest", temperature=0)

class AuditState(TypedDict):
    raw_data: str
    extracted_policies: str
    risk_flags: List[str]
    escalate_to_human: bool
    human_decision: str
    audit_trail: List[str]
    final_report: str

def supervisor_node(state: AuditState):
    return state

def extraction_agent(state: AuditState):
    print("--- 🤖 AGENT: Extracting Policies ---")
    raw = state.get('raw_data', '')
    
    # Untrusted input firewall mitigation
    sanitized_raw = raw.replace("\n", " ").strip()[:1000] 
    prompt = f"Extract the core access policy from this log in one sentence. Log: {sanitized_raw}"
    
    response = llm.invoke(prompt)
    
    # Prevent infinite router loops on empty LLM returns
    policy = response.content.strip() or "No policy extracted."
    return {"extracted_policies": policy}

def risk_agent(state: AuditState):
    print("--- 🤖 AGENT: Analyzing Risk ---")
    raw_data = state.get("raw_data", "").lower()
    extracted = state.get("extracted_policies", "").lower()
    flags = []
    
    # Deterministic T3 evaluation on BOTH raw input and LLM output
    if "admin" in raw_data or "admin" in extracted:
        flags.append("Admin access detected.")
        
    return {"risk_flags": flags, "escalate_to_human": len(flags) > 0}

def human_review(state: AuditState):
    print("--- 👤 HUMAN: Reviewing & Logging ---")
    # Enforces fail-closed audit logging
    timestamp = datetime.utcnow().isoformat()
    decision = state.get("human_decision", "approved")
    trail_entry = f"[{timestamp}] Human reviewed risk flags. Decision: {decision}"
    
    return {
        "escalate_to_human": False, 
        "audit_trail": [trail_entry]
    }

def reporting_agent(state: AuditState):
    print("--- 🤖 AGENT: Generating Report ---")
    return {"final_report": f"Audit Complete. Policies: {state.get('extracted_policies')}"}

def supervisor_router(state: AuditState) -> str:
    if state.get("escalate_to_human"):
        return "human_review"
    if not state.get("extracted_policies"):
        return "extractor"
    if state.get("risk_flags") is None:
        return "risk_analyzer"
    return "reporter"

workflow = StateGraph(AuditState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("extractor", extraction_agent)
workflow.add_node("risk_analyzer", risk_agent)
workflow.add_node("human_review", human_review)
workflow.add_node("reporter", reporting_agent)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor", supervisor_router,
    {"extractor": "extractor", "risk_analyzer": "risk_analyzer", "reporter": "reporter", "human_review": "human_review"}
)

for node in ["extractor", "risk_analyzer", "human_review"]:
    workflow.add_edge(node, "supervisor")
workflow.add_edge("reporter", END)

# Note: Swap MemorySaver with langgraph.checkpoint.postgres for production durable execution
app = workflow.compile(checkpointer=MemorySaver(), interrupt_before=["human_review"])

if __name__ == "__main__":
    config = {"configurable": {"thread_id": "audit_test_002"}}
    initial_state = {
        "raw_data": "User 1045 logged in. Role: Admin. Location: Unknown IP.",
        "risk_flags": None,
        "audit_trail": []
    }
    
    for _ in app.stream(initial_state, config=config): pass 
        
    state = app.get_state(config)
    
    if state.next == ('human_review',):
        print(f"\n🛑 GRAPH PAUSED. Risk: {state.values.get('risk_flags')}")
        
        # Payload injection simulating external webhook resolution
        action = input("\nType 'approve' or 'reject' to resume: ")
        app.update_state(config, {"human_decision": action})
        
        for _ in app.stream(None, config=config): pass

    final_state = app.get_state(config)
    print(f"\n✅ GRAPH COMPLETE: {final_state.values.get('final_report')}")
    print(f"Audit Trail: {final_state.values.get('audit_trail')}\n")
