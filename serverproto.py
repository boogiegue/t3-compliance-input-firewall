from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid

# Import your compiled LangGraph app from main.py
from main import app as langgraph_app

app = FastAPI(title="T3 Compliance Supervisor API")

# Define the expected JSON payload from n8n
class WebhookPayload(BaseModel):
    raw_log_text: str
    thread_id: str = None  # Optional: allows n8n to resume paused workflows

@app.post("/webhook/triage")
async def process_log(payload: WebhookPayload):
    try:
        # Generate a unique thread ID if n8n didn't provide one
        thread_id = payload.thread_id or f"triage_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_state = {
            "raw_data": payload.raw_log_text,
            "risk_flags": None,
            "audit_trail": []
        }
        
        # Execute the graph
        for _ in langgraph_app.stream(initial_state, config=config):
            pass
            
        state = langgraph_app.get_state(config)
        
        # Check if the T3 boundary paused the graph for human review
        if state.next == ('human_review',):
            return {
                "status": "PAUSED_FOR_REVIEW",
                "thread_id": thread_id,
                "risk_flags": state.values.get("risk_flags"),
                "message": "Workflow halted. Send human decision via /webhook/approve endpoint."
            }
            
        # If it passed without triggering escalation
        return {
            "status": "COMPLETED",
            "thread_id": thread_id,
            "report": state.values.get("final_report")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Runs the server locally on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
