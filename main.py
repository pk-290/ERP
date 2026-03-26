from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path
import time
import uvicorn
import os
import sys

# Ensure the parent directory is in the path so we can import agent and graph_rag
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from wrapper import get_logger
from agent.service import ask_erp_agent, clear_session
from graph_rag.kuzu_store import get_connection, get_database

logger = get_logger("api")
app = FastAPI(title="ERP AI Agent API")

# Configure CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend URL
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info("POST /api/chat | session=%s | query=%r", request.session_id, request.query[:120])
    t0 = time.perf_counter()
    try:
        response_text = ask_erp_agent(request.session_id, request.query)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("POST /api/chat OK | session=%s | %.0f ms | response_len=%d",
                    request.session_id, elapsed, len(response_text))
        return ChatResponse(response=response_text)
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("POST /api/chat FAILED | session=%s | %.0f ms | %s: %s",
                     request.session_id, elapsed, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/{session_id}")
async def reset_session(session_id: str):
    logger.info("DELETE /api/chat/%s | session cleared", session_id)
    clear_session(session_id)
    return {"status": "session cleared"}

@app.get("/api/graph")
async def get_graph_data():
    """
    Returns the Order-to-Cash (O2C) subgraph for Cytoscape visualization.
    Traverses: Customer → SalesOrder → Delivery → BillingDocument → JournalEntry
    Skips AVAILABLE_AT (3036 noisy Product→Plant edges) to keep the graph clean.
    Each node includes a 'tier' field for hierarchical layout.
    """
    db = get_database()
    conn = get_connection(db)

    TIERS = {
        "Customer": 0,
        "SalesOrder": 1,
        "Delivery": 2,
        "BillingDocument": 3,
        "JournalEntry": 4,
    }

    def short_label(node, table_name):
        # Prefer entity_id (e.g. "SO100001"), then name, then strip type prefix from node_id
        eid = node.get("entity_id")
        if eid:
            return str(eid)
        name = node.get("name")
        if name:
            return str(name)
        nid = str(node["node_id"])
        # Strip table name prefix (e.g. "JournalEntry84900000246" → "84900000246")
        stripped = nid.replace(table_name, "").lstrip("_")
        return stripped if stripped else nid

    try:
        elements = []
        nodes_seen = set()
        edges_seen = set()

        def add_node(node, table_name):
            nid = str(node["node_id"])
            if nid in nodes_seen:
                return nid
            nodes_seen.add(nid)
            elements.append({
                "data": {
                    "id": nid,
                    "label": short_label(node, table_name),
                    "type": table_name,
                    "tier": TIERS.get(table_name, 2),
                },
                "group": "nodes"
            })
            return nid

        def add_edge(src_id, dst_id, rel_name):
            eid = f"{src_id}__{rel_name}__{dst_id}"
            if eid in edges_seen:
                return
            edges_seen.add(eid)
            elements.append({
                "data": {
                    "id": eid,
                    "source": str(src_id),
                    "target": str(dst_id),
                    "label": rel_name,
                },
                "group": "edges"
            })

        # Step 1: Customer → SalesOrder (all orders, ~100)
        res = conn.execute(
            "MATCH (c:Customer)-[:PLACED_ORDER]->(so:SalesOrder) RETURN c, so"
        )
        while res.has_next():
            c, so = res.get_next()
            cid = add_node(c, "Customer")
            soid = add_node(so, "SalesOrder")
            add_edge(cid, soid, "PLACED_ORDER")

        # Step 2: SalesOrder → Delivery
        res = conn.execute(
            "MATCH (so:SalesOrder)-[:DELIVERED_BY]->(d:Delivery) RETURN so.node_id, d"
        )
        while res.has_next():
            so_id, d = res.get_next()
            so_id = str(so_id)
            if so_id not in nodes_seen:
                continue
            did = add_node(d, "Delivery")
            add_edge(so_id, did, "DELIVERED_BY")

        # Step 3: Delivery → BillingDocument
        res = conn.execute(
            "MATCH (d:Delivery)-[:INVOICED_BY]->(b:BillingDocument) RETURN d.node_id, b"
        )
        while res.has_next():
            d_id, b = res.get_next()
            d_id = str(d_id)
            if d_id not in nodes_seen:
                continue
            bid = add_node(b, "BillingDocument")
            add_edge(d_id, bid, "INVOICED_BY")

        # Step 4: BillingDocument → JournalEntry
        res = conn.execute(
            "MATCH (b:BillingDocument)-[:POSTED_AS]->(j:JournalEntry) RETURN b.node_id, j"
        )
        while res.has_next():
            b_id, j = res.get_next()
            b_id = str(b_id)
            if b_id not in nodes_seen:
                continue
            jid = add_node(j, "JournalEntry")
            add_edge(b_id, jid, "POSTED_AS")

        # Step 5: BillingDocument cancellations (only between already-known nodes)
        res = conn.execute(
            "MATCH (b1:BillingDocument)-[:CANCELS]->(b2:BillingDocument) RETURN b1.node_id, b2.node_id"
        )
        while res.has_next():
            b1_id, b2_id = res.get_next()
            b1_id, b2_id = str(b1_id), str(b2_id)
            if b1_id in nodes_seen and b2_id in nodes_seen:
                add_edge(b1_id, b2_id, "CANCELS")

        node_count = sum(1 for e in elements if e["group"] == "nodes")
        edge_count = sum(1 for e in elements if e["group"] == "edges")
        logger.info("GET /api/graph | nodes=%d edges=%d", node_count, edge_count)
        return {"elements": elements}

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    logger.info("ERP Agent API starting up on port %s", os.getenv("PORT", "8000"))

    # In production (Docker/Render), serve the pre-built React frontend.
    # Controlled by the SERVE_FRONTEND env var set in the Dockerfile.
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if os.getenv("SERVE_FRONTEND") == "true" and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
        logger.info("Serving frontend from %s", frontend_dist)
    else:
        logger.info("Frontend static serving disabled (dev mode or dist not built)")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
