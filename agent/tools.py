"""
Langchain tools for the ERP Graph AI Agent.
These tools allow the agent to inspect the Kuzu graph schema and execute
raw Cypher to explore the dataset and perform complex analytical queries.
"""
import sys
import time
from pathlib import Path
from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from wrapper import get_logger
from graph_rag.kuzu_query import get_schema_description, run_cypher

logger = get_logger("agent.tools")


class CypherQueryInput(BaseModel):
    query: str = Field(
        description="A raw Cypher query string to execute against the Kuzu database. Use exactly the column names and node/relationship types provided by the schema."
    )


class DatabaseSchemaTool(BaseTool):
    """
    Returns the complete schema of the Kuzu graph database, including all
    node tables, relationship tables, and their exact column names/properties.
    """
    name: str = "get_database_schema"
    description: str = "Returns the schema for the ERP Kuzu Graph Database. Call this first if you don't know the exact names of tables (node/relationship types) or their properties."
    return_direct: bool = False

    def _run(self) -> str:
        logger.info("[TOOL] get_database_schema called")
        t0 = time.perf_counter()
        result = get_schema_description()
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("[TOOL] get_database_schema done | %.0f ms | result_len=%d", elapsed, len(result))
        return result


class RunCypherTool(BaseTool):
    """
    Executes a Cypher query against the Kuzu database and returns the structured
    output as a string map.
    """
    name: str = "execute_cypher_query"
    description: str = (
        "Executes a Cypher query against the Kuzu database and returns the results. "
        "Use this for analytical questions, multi-hop lookups, or exploring the data. "
        "IMPORTANT: Kuzu Cypher is strict. Use EXACT property names. Return only the columns you need. "
        "Example: MATCH (c:Customer)-[:PLACED_ORDER]->(o:SalesOrder) RETURN c.name, count(o) AS order_count ORDER BY order_count DESC LIMIT 5"
    )
    args_schema: Type[BaseModel] = CypherQueryInput
    return_direct: bool = False

    def _run(self, query: str) -> str:
        # Prevent mutating the database if the agent goes rogue
        if any(kw in query.upper() for kw in ("CREATE", "MERGE", "DELETE", "SET")):
            logger.warning("[TOOL] execute_cypher_query BLOCKED (write attempt) | query=%r", query[:200])
            return "Error: Database is READ-ONLY for the agent. Please only use MATCH queries."

        logger.info("[TOOL] execute_cypher_query | query=%r", query[:200])
        t0 = time.perf_counter()
        try:
            result = run_cypher(query)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("[TOOL] execute_cypher_query done | %.0f ms | result_len=%d", elapsed, len(str(result)))
            return result
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("[TOOL] execute_cypher_query FAILED | %.0f ms | %s: %s",
                         elapsed, type(exc).__name__, exc)
            raise


# List of all tools to bind to the agent
ERP_TOOLS = [DatabaseSchemaTool(), RunCypherTool()]
