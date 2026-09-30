import os
from typing import TypedDict, Annotated, List
import operator
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Load environment variables from .env
load_dotenv()

# Initialize Claude
llm = ChatAnthropic(model="claude-3-haiku-20240307", temperature=0)

# 1. Define the State Schema
class AuditState(TypedDict):
    raw_data: str
    extracted_policies: str
    risk_flags: List[str]
    escalate_to_human: bool
    final_report: str

# 2. Define the Nodes (Workers & Supervisor)
def supervisor_node(state: AuditState):
    # Hub node: just passes state forward to the router
    return state

def extraction_agent(state: AuditState):
    print("--- 🤖 AGENT: Extracting Policies ---")
    # T1: Using Claude to extract data
    prompt = f"Extract the core access policy from this raw log in one sentence: {state.get('raw_data')}"
    response = llm.invoke(prompt)
    return {"extracted_policies": response.content}

def risk_agent(state: AuditState):
    print("--- 🤖 AGENT: Analyzing Risk ---")
    # T3 Deterministic evaluation for portfolio demonstration
    policies = state.get("extracted_policies", "")
    flags = []
    
    if "admin" in policies.lower():
        flags.append("Admin access detected in raw logs.")
        
    # Trigger escalation if flags exist
    return {"risk_flags": flags, "escalate_to_human": len(flags) > 0}

def human_review(state: AuditState):
    print("--- 👤 HUMAN: Reviewing & Approving ---")
    # In production, this happens via API payload. Here we just clear the flag.
    return {"escalate_to_human": False}

def reporting_agent(state: AuditState):
    print("--- 🤖 AGENT: Generating Report ---")
    return {"final_report": f"Audit Complete. Policies: {state.get('extracted_policies')}"}

# 3. Define the Routing Logic
def supervisor_router(state: AuditState) -> str:
    if state.get("escalate_to_human"):
        return "human_review"
    if not state.get("extracted_policies"):
        return "extractor"
    if not state.get("risk_flags") and state.get("risk_flags") != []:
        # If risk_flags is None, it hasn't run yet
        return "risk_analyzer"
    return "reporter"

# 4. Build the Graph
workflow = StateGraph(AuditState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("extractor", extraction_agent)
workflow.add_node("risk_analyzer", risk_agent)
workflow.add_node("human_review", human_review)
workflow.add_node("reporter", reporting_agent)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {
        "extractor": "extractor",
        "risk_analyzer": "risk_analyzer",
        "reporter": "reporter",
        "human_review": "human_review"
    }
)

workflow.add_edge("extractor", "supervisor")
workflow.add_edge("risk_analyzer", "supervisor")
workflow.add_edge("human_review", "supervisor")
workflow.add_edge("reporter", END)

# 5. Compile with Persistent Memory
memory = MemorySaver()
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["human_review"] # Tell graph to pause BEFORE this node
)

# 6. Execute the Test
if __name__ == "__main__":
    print("\nStarting Workflow Execution...")
    
    # We use a thread ID to track the memory state
    config = {"configurable": {"thread_id": "audit_test_001"}}
    
    initial_state = {
        "raw_data": "User 1045 logged in. Role: Admin. Location: Unknown IP.",
        "risk_flags": None
    }
    
    # Run the graph until it hits the interrupt or finishes
    for event in app.stream(initial_state, config=config):
        pass 
        
    state = app.get_state(config)
    
    if state.next == ('human_review',):
        print(f"\n🛑 GRAPH PAUSED: Workflow interrupted. Risk flagged: {state.values.get('risk_flags')}")
        print("Waiting for human approval...")
        
        # Simulating the human clicking "Approve" in Slack/n8n later
        input("\nPress Enter to simulate human approval and resume graph...")
        
        # Resume graph with the exact same config (thread_id)
        for event in app.stream(None, config=config):
            pass

    final_state = app.get_state(config)
    print(f"\n✅ GRAPH COMPLETE: {final_state.values.get('final_report')}\n")
