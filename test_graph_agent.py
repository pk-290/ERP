"""
Test script for the ERP Graph AI Agent.
Runs a set of test queries and prints the agent's response and tool calls.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from agent.graph_agent import create_erp_agent
from langchain_core.messages import HumanMessage
from wrapper import get_logger

logger = get_logger("test.graph_agent")

def test_query(agent, query: str):
    print(f"\n{'='*80}")
    print(f"QUESTION: {query}")
    print(f"{'='*80}\n")
    
    try:
        # We use invoke to get the full final state
        response = agent.invoke({"messages": [HumanMessage(content=query)]})
        
        # Print the messages to see the thought process (tool calls and results)
        for msg in response["messages"]:
            role = "USER" if isinstance(msg, HumanMessage) else "AGENT"
            print(f"[{role}]: {msg.content}")
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"   🛠️  TOOL CALL: {tc['name']}({tc['args']})")
            if hasattr(msg, "type") and msg.type == "tool":
                print(f"   📦 TOOL RESULT: {msg.content[:200]}...")
        
        print(f"\nFINAL ANSWER:\n{response['messages'][-1].content}")
        
    except Exception as e:
        print(f"❌ Error during agent execution: {e}")
        logger.exception("Agent execution failed")

def main():
    print("🚀 Initializing ERP Graph Agent...")
    agent = create_erp_agent()
    
    test_queries = [
        "How many customers are in the database?",
        "What is the total outstanding amount for customers in Mumbai?",
        "Which products were included in Sales Order 740506?",
        "Compare the requested delivery date and actual delivery date for Sales Order 740506 to see if it was on time."
    ]
    
    for query in test_queries:
        test_query(agent, query)

if __name__ == "__main__":
    main()
