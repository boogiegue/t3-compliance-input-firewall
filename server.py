from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

# Import your compiled LangGraph app from main.py
from main import app as langgraph_app

app = FastAPI(title="T3 Compliance Supervisor API")

# --- Schemas ---
class WebhookPayload(BaseModel):
    raw_log_text: str
    thread_id: str = None

class ApprovalPayload(BaseModel):
    thread_id: str
    decision: str  # "approve" or "reject"
    approver_id: str

# --- Endpoints ---
@app.post("/webhook/triage")
async def process_log(payload: WebhookPayload):
    try:
        thread_id = payload.thread_id or f"triage_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = {
            "raw_data": payload.raw_log_text,
            "risk_flags": None,
            "audit_trail": []
        }
        
        for _ in langgraph_app.stream(initial_state, config=config):
            pass
            
        state = langgraph_app.get_state(config)
        
        if state.next == ('human_review',):
            return {
                "status": "PAUSED_FOR_REVIEW",
                "thread_id": thread_id,
                "risk_flags": state.values.get("risk_flags"),
                "raw_input": state.values.get("raw_data"),             # Added context
                "llm_summary": state.values.get("extracted_policies"), # Added context
                "message": "Workflow halted. Send human decision via /webhook/approve endpoint."
            }
            
        return {
            "status": "COMPLETED",
            "thread_id": thread_id,
            "report": state.values.get("final_report")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/approve")
async def submit_approval(payload: ApprovalPayload):
    try:
        config = {"configurable": {"thread_id": payload.thread_id}}
        state = langgraph_app.get_state(config)

        # Verify the graph is actually paused and waiting for human review
        if state.next != ('human_review',):
            raise HTTPException(status_code=400, detail="This thread is not paused for human review.")

        if payload.decision not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'.")

        # Inject the human decision into the graph's state
        langgraph_app.update_state(
            config, 
            {"human_decision": payload.decision, "approver_id": payload.approver_id}
        )

        # Resume execution (passing None tells it to continue from the pause)
        for _ in langgraph_app.stream(None, config=config):
            pass

        final_state = langgraph_app.get_state(config)

        return {
            "status": "COMPLETED",
            "thread_id": payload.thread_id,
            "report": final_state.values.get("final_report")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
