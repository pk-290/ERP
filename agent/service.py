"""
Service layer exposing the ERP AI Agent for backend (e.g. FastAPI) usage.
Maintains conversational state per session.
"""
import sys
import time
from pathlib import Path
from typing import Dict, List

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

# Ensure project root is on path (needed when imported by main.py)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from wrapper import get_logger
from .graph_agent import create_erp_agent

logger = get_logger("agent.service")

# Simple in-memory session store.
# For production, replace with Redis/Postgres Langchain History.
SESSION_STORE: Dict[str, List[BaseMessage]] = {}

# Initialize the global agent executor
logger.info("Initialising ERP agent executor …")
agent_executor = create_erp_agent()
logger.info("ERP agent executor ready")


def ask_erp_agent(session_id: str, query: str) -> str:
    """
    Handles a user query, invoking the agent with historical context,
    and returns the final response string.

    Args:
        session_id: Unique identifier for the conversation
        query: User's natural language question
    """
    is_new = session_id not in SESSION_STORE
    if is_new:
        SESSION_STORE[session_id] = []
        logger.info("[%s] New session started", session_id)

    chat_history = SESSION_STORE[session_id]
    history_len = len(chat_history)
    logger.info("[%s] Invoking agent | history_msgs=%d | query=%r",
                session_id, history_len, query[:120])

    # LangGraph expects a list of messages. Append the new human message.
    current_messages = chat_history + [HumanMessage(content=query)]

    t0 = time.perf_counter()
    try:
        response = agent_executor.invoke({"messages": current_messages})
        elapsed = (time.perf_counter() - t0) * 1000

        final_message = response["messages"][-1]
        output = final_message.content

        # Count how many tool-call steps the agent took
        tool_steps = sum(
            1 for m in response["messages"]
            if hasattr(m, "type") and m.type == "tool"
        )

        logger.info("[%s] Agent finished | %.0f ms | tool_steps=%d | response_len=%d",
                    session_id, elapsed, tool_steps, len(output))

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("[%s] Agent invocation failed | %.0f ms | %s: %s",
                     session_id, elapsed, type(exc).__name__, exc)
        raise

    # Update conversation history
    chat_history.append(HumanMessage(content=query))
    chat_history.append(AIMessage(content=output))

    # Keep history bounded to avoid massive token costs (last 10 messages)
    if len(chat_history) > 10:
        SESSION_STORE[session_id] = chat_history[-10:]
        logger.debug("[%s] History trimmed to last 10 messages", session_id)

    return output


def clear_session(session_id: str):
    """Clears the history for a given session."""
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
        logger.info("[%s] Session cleared", session_id)
    else:
        logger.debug("[%s] clear_session called but no session found", session_id)
