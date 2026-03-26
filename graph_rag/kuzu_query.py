"""
Cypher query interface for Kuzu graph database.
Provides helper functions designed to be used by the AI agent to easily
introspect the schema and run queries.
"""
from typing import Any

import kuzu
from pydantic import BaseModel

from .kuzu_store import NODE_SCHEMAS, REL_SCHEMAS, get_connection, get_database


class QueryResult(BaseModel):
    """Structured response for an LLM to parse easily."""
    columns: list[str]
    rows: list[list[Any]]


def get_schema_description() -> str:
    """
    Returns a clean, prompt-friendly string describing the entire
    Kuzu graph database schema (nodes, relationships, and their properties).
    """
    lines = ["# Kuzu Graph Database Schema"]
    
    lines.append("\n## Node Tables")
    for node_type, props in NODE_SCHEMAS.items():
        lines.append(f"- **{node_type}**")
        prop_str = ", ".join(props.keys())
        lines.append(f"  Properties: {prop_str}")
        
    lines.append("\n## Relationship Tables")
    for rel_type, schema in REL_SCHEMAS.items():
        from_t = schema["from"]
        to_t = schema["to"]
        lines.append(f"- **{rel_type}** ({from_t} → {to_t})")
        if schema["props"]:
            prop_str = ", ".join(schema["props"].keys())
            lines.append(f"  Properties: {prop_str}")
        else:
            lines.append("  Properties: <none>")
            
    return "\n".join(lines)


def run_cypher(query: str, params: dict | None = None) -> str:
    """
    Executes a Cypher query against the Kuzu DB and returns a formatted
    string of the results, specifically optimized for LLM readability.
    
    Args:
        query: The Cypher query string
        params: Optional dictionary of query parameters
    """
    db = get_database()  # Connects to default graph_rag/output/kuzu_db
    conn = get_connection(db)
    
    try:
        if params is None:
            params = {}
            
        result = conn.execute(query, params)
        
        # Get column names
        columns = result.get_column_names()
        
        # Extract rows
        rows = []
        while result.has_next():
            row = result.get_next()
            # Clean up the row data (e.g. handle internal node dicts if they returned full nodes)
            clean_row = []
            for item in row:
                if isinstance(item, dict) and "_label" in item:
                    # It's an entire node or edge object
                    clean_row.append(f"<{item['_label']} {item.get('node_id', '')}>")
                else:
                    clean_row.append(str(item))
            rows.append(clean_row)
            
        if not rows:
            return "Query executed successfully, but returned 0 rows."
            
        # Format as a simple markdown table or aligned text
        # We'll use a simple dictionary-like string representation for compactness
        output = [f"Columns: {', '.join(columns)}", f"Total Rows: {len(rows)}", "-" * 40]
        
        # Cap output to avoid blowing up LLM context
        MAX_ROWS = 50
        for i, row in enumerate(rows[:MAX_ROWS]):
            row_dict = {col: val for col, val in zip(columns, row)}
            output.append(str(row_dict))
            
        if len(rows) > MAX_ROWS:
            output.append(f"... (truncating {len(rows) - MAX_ROWS} more rows)")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Error executing Cypher query: {str(e)}"
