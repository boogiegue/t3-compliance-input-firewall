# T3 Compliance Supervisor: Untrusted Input Firewall

A deterministic security boundary for LLM-driven automation. This FastAPI microservice physically separates probabilistic reasoning (Anthropic Claude 3.5) from deterministic execution (Python/LangGraph), ensuring that Generative AI workflows fail closed under prompt injection or hallucination.

## The Architecture (T0-T3 Risk Tiering)
* **T1 (Probabilistic):** Claude attempts to extract data from raw webhook text (e.g., n8n, Zendesk, Email).
* **T3 (Deterministic):** A LangGraph routing layer strictly evaluates the output against hardcoded risk vectors (e.g., regex pattern matching for privilege escalation).
* **Human-in-the-Loop (HITL):** If a T3 boundary is breached, the graph physically pauses execution, holds the state in memory, and returns a webhook demanding a 2-step manual approval via external platforms (Slack/Telegram).

## Endpoints
* `POST /webhook/triage`: Ingests untrusted logs/emails, runs the dual-layer audit, and returns either a `COMPLETED` payload or a `PAUSED_FOR_REVIEW` state.
* `POST /webhook/approve`: Re-enters the specific memory thread to inject the human approver's ID and decision, unpausing the workflow.
