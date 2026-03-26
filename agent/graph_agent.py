"""
Core Langchain agent executor definition using LangGraph's ReAct pattern.
"""
import sys
from pathlib import Path

# Add project root to path so we can import from gemini_utils and wrapper
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from langgraph.prebuilt import create_react_agent
from gemini_utils import get_latest_gemini_llm
from wrapper import get_logger

from .tools import ERP_TOOLS
from .prompts import SYSTEM_PROMPT

logger = get_logger("agent.graph_agent")


def create_erp_agent():
    """
    Creates and returns a LangGraph ReAct agent initialized with the
    Gemini LLM, Kuzu Graph tools, and the ERP-specific system prompt.
    """
    logger.info("Creating ERP ReAct agent | model=gemini-pro | tools=%s",
                [t.name for t in ERP_TOOLS])

    # Use "pro" for complex reasoning tasks like Cypher generation
    llm = get_latest_gemini_llm("flash")
    logger.info("LLM loaded: %s", type(llm).__name__)

    # create_react_agent automatically handles tool calling and error retries
    agent = create_react_agent(llm, tools=ERP_TOOLS, prompt=SYSTEM_PROMPT)

    logger.info("ERP ReAct agent created successfully")
    return agent
