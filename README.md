# ERP Intelligence Agent

A full-stack AI agent that lets you query your ERP data in plain English. It models the complete Order-to-Cash (O2C) business process as a knowledge graph, exposes it via a LangGraph ReAct agent backed by Gemini Flash, and visualises the live graph in a React dashboard.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                    │
│                                                                 │
│   ┌─────────────────────┐      ┌─────────────────────────────┐ │
│   │   GraphPanel        │      │   ChatPanel                 │ │
│   │   (Cytoscape.js)    │      │   POST /api/chat            │ │
│   │   GET /api/graph    │      │   DELETE /api/chat/:session │ │
│   └────────┬────────────┘      └──────────────┬──────────────┘ │
└────────────┼──────────────────────────────────┼────────────────┘
             │  (Vite proxy in dev /             │
             │   same origin in prod)            │
             ▼                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend  (main.py)                    │
│                                                                 │
│   GET  /api/graph    ──►  Kuzu Cypher queries (5 hops O2C)     │
│   GET  /api/health   ──►  healthcheck                          │
│   POST /api/chat     ──►  agent/service.py                     │
│   DELETE /api/chat   ──►  session store clear                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  LangGraph ReAct Agent                          │
│                                                                 │
│   agent/service.py                                             │
│   ├─ In-memory session store  (last 10 msgs per session)       │
│   └─ agent_executor.invoke(messages)                           │
│                                                                 │
│   agent/graph_agent.py                                         │
│   └─ create_react_agent(llm=GeminiFlash, tools, prompt)        │
│                                                                 │
│   agent/tools.py                                               │
│   ├─ get_database_schema  → returns full Kuzu schema string    │
│   └─ execute_cypher_query → runs MATCH queries, returns table  │
│                                                                 │
│   agent/prompts.py                                             │
│   └─ SYSTEM_PROMPT  (live schema embedded at startup)          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               Kuzu Embedded Graph Database                      │
│               graph_rag/output/kuzu_db/                        │
│                                                                 │
│   7 Node types:  Customer, Product, Plant, SalesOrder,         │
│                  Delivery, BillingDocument, JournalEntry        │
│                                                                 │
│   12 Rel types:  PLACED_ORDER, DELIVERED_BY, INVOICED_BY,      │
│                  POSTED_AS, ORDER_CONTAINS, CANCELS, ...       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ (built once by ETL pipeline)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│          graph_rag/ ETL Pipeline                                │
│                                                                 │
│   sample_data/  (JSONL files from SAP-like export)             │
│   ──► loader.py   (read & normalise JSONL)                     │
│   ──► nodes.py    (build enriched node dicts)                  │
│   ──► edges.py    (derive relationships)                       │
│   ──► graph_builder.py  (assemble graph.json)                  │
│   ──► kuzu_store.py     (ETL graph.json → Kuzu schema+data)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Design Choices

### 1. Kuzu as the Graph Database
Kuzu is an **embedded** graph database (like SQLite, but for graphs). There is no separate database process to manage, authenticate against, or keep alive. The entire database lives in `graph_rag/output/kuzu_db/` as a directory of files. This made it the right call for a self-contained backend that can be bundled into a Docker image.

Kuzu speaks **Cypher**, the same query language as Neo4j, which means the LLM can generate queries without learning a proprietary API.

### 2. LangGraph ReAct Agent (not a simple LLM call)
Instead of a one-shot prompt, the agent uses the **ReAct (Reason + Act)** loop:
1. The LLM reasons about the question
2. It calls a tool (`get_database_schema` or `execute_cypher_query`)
3. It observes the result
4. It repeats until confident, then returns a final answer

This is critical for ERP data because most business questions require multiple queries (e.g., "who are my slow payers?" needs schema lookup → COUNT/AVG query → interpretation).

### 3. Schema Embedded in System Prompt
The full Kuzu schema is fetched **once at startup** and injected directly into the system prompt (`SYSTEM_PROMPT` in `agent/prompts.py`). This saves one tool-call round-trip on every question. The `get_database_schema` tool still exists as a fallback for when the schema drops out of context on long conversations.

### 4. All Properties as STRING in Kuzu
Every node and relationship property is stored as `STRING`. This was a deliberate trade-off: it avoids ETL type-coercion failures when SAP exports have inconsistent number formatting, null values, or mixed types. The cost is that **all numerical comparisons require explicit `CAST`** in Cypher (e.g., `CAST(je.amount, "DOUBLE")`). This rule is enforced in the system prompt.

### 5. Observability Stack
Two independent layers of observability:

| Layer | Tool | What it captures |
|---|---|---|
| Structured logging | `wrapper.py` + Python `logging` | Every API request, session state, tool call, timing, errors |
| LLM tracing | Langfuse (`gemini_utils.py`) | Full LLM chain traces, token counts, latency per step |

Logs are written to both **stdout** (INFO+) and **`logs/agent.log`** (DEBUG+, full detail).

### 6. Vite Proxy for Local Dev
In development, Vite proxies all `/api/*` requests from port 5173 to the FastAPI server on port 8000 (`vite.config.js`). In production (Docker), both the API and the built frontend static files are served from the **same FastAPI process on a single port**, eliminating CORS entirely.

### 7. Session Memory (Bounded)
Conversation history is kept in a simple in-memory Python dict keyed by `session_id`. History is hard-capped at **10 messages** (5 turns) to prevent unbounded token cost. For production scale, replace `SESSION_STORE` in `service.py` with a Redis-backed LangChain `RedisChatMessageHistory`.

---

## Project Structure

```
ERP/
├── main.py                        # FastAPI app — all HTTP routes
├── wrapper.py                     # Centralised logger + decorators
├── gemini_utils.py                # Gemini LLM + Langfuse setup
├── requirements.txt
├── Dockerfile
│
├── agent/
│   ├── graph_agent.py             # LangGraph ReAct agent factory
│   ├── service.py                 # Session management + agent runner
│   ├── tools.py                   # Kuzu schema + Cypher tools
│   ├── prompts.py                 # System prompt with live schema
│   └── cli.py                     # Rich terminal REPL for testing
│
├── graph_rag/
│   ├── config.py                  # Paths + field-name mappings
│   ├── loader.py                  # JSONL → raw dicts
│   ├── nodes.py                   # Build enriched node objects
│   ├── edges.py                   # Derive relationships
│   ├── graph_builder.py           # Assemble graph.json
│   ├── kuzu_store.py              # ETL graph.json → Kuzu DB
│   ├── kuzu_query.py              # Schema helper + Cypher runner
│   └── output/
│       ├── graph.json             # Intermediate graph representation
│       └── kuzu_db/               # Kuzu binary database (committed)
│
├── sample_data/                   # Raw JSONL exports (SAP-format)
│   ├── business_partners/
│   ├── sales_order_headers/
│   ├── outbound_delivery_headers/
│   ├── billing_document_headers/
│   ├── journal_entry_items_accounts_receivable/
│   └── ...
│
├── frontend/
│   ├── vite.config.js             # Dev proxy → localhost:8000
│   ├── src/
│   │   ├── App.jsx                # Layout: GraphPanel (left) + ChatPanel (right)
│   │   ├── components/
│   │   │   ├── GraphPanel.jsx     # Cytoscape.js O2C graph
│   │   │   └── ChatPanel.jsx      # Agent chat UI
│   │   └── App.css
│   └── package.json
│
└── logs/
    └── agent.log                  # Runtime log file
```

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Google AI Studio API key ([get one free](https://aistudio.google.com/))
- (Optional) Langfuse account for LLM tracing

### 1. Clone and configure environment

```bash
git clone <your-repo>
cd ERP

cp .env.example .env   # or create .env manually
```

Add to `.env`:
```env
GOOGLE_API_KEY=your_google_api_key_here

# Optional — Langfuse tracing (leave blank to disable)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 2. Backend

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (First time only) Build the Kuzu graph database from JSONL source data
# Skip this if graph_rag/output/kuzu_db/ already exists in the repo
python -m graph_rag.kuzu_store

# Start the API server
uvicorn main:app --reload --port 8000
```

The API will be at `http://localhost:8000`. You can verify it with:
```bash
curl http://localhost:8000/api/health
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite proxy will forward all `/api/*` calls to the backend automatically.

### 4. CLI (optional — for quick agent testing without the UI)

```bash
# From the project root with venv active
python -m agent.cli
```

---

## Render Deployment

### GitHub alone vs. Dockerfile — the short answer

**Use the Dockerfile.** Here's why:

| | GitHub native | Dockerfile |
|---|---|---|
| Frontend | ❌ Render can't build+serve React alongside Python automatically | ✅ React built inside the image, served by FastAPI |
| Kuzu DB | ⚠️ Works only if `kuzu_db/` is committed to git | ✅ Copied or rebuilt deterministically during build |
| Single service | ❌ Needs two Render services (Web Service + Static Site) | ✅ One service, one port |
| Environment | ✅ | ✅ |

If you commit `graph_rag/output/kuzu_db/` and don't mind two separate Render services (a Web Service for the API + a Static Site for the frontend), GitHub native can work. But Docker is simpler and more production-safe.

### Dockerfile

```dockerfile
# See Dockerfile in the repo root
```

### Steps to deploy on Render

1. **Push your repo to GitHub** (make sure `graph_rag/output/kuzu_db/` and `graph_rag/output/graph.json` are committed and NOT in `.gitignore`)

2. **Go to [render.com](https://render.com)** → New → Web Service

3. **Connect your GitHub repo**

4. **Configure the service:**
   - Environment: `Docker`
   - Dockerfile path: `./Dockerfile`
   - Port: `8000`

5. **Add environment variables** in Render dashboard:
   ```
   GOOGLE_API_KEY        = your_key
   LANGFUSE_PUBLIC_KEY   = (optional)
   LANGFUSE_SECRET_KEY   = (optional)
   LANGFUSE_HOST         = https://cloud.langfuse.com
   ```

6. **Deploy.** Render will build the Docker image, run the container, and give you a public URL.

> **Note on disk:** Kuzu is embedded and reads from the filesystem. Render's free tier has an **ephemeral** filesystem — any writes are lost on restart. This is fine because the Kuzu DB is read-only at runtime (the agent only runs `MATCH` queries). If you ever need to rebuild the DB at runtime, upgrade to a Render Disk.

---

## Adding New Data

To ingest a new set of JSONL exports:

1. Drop the files into the appropriate `sample_data/<entity>/` folder
2. Re-run the ETL pipeline:
   ```bash
   python -m graph_rag.run_pipeline     # rebuilds graph.json
   python -m graph_rag.kuzu_store       # rebuilds kuzu_db from graph.json
   ```
3. Restart the API server (the schema is read at startup)

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ Yes | Google AI Studio key for Gemini models |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse project public key (tracing) |
| `LANGFUSE_SECRET_KEY` | No | Langfuse project secret key (tracing) |
| `LANGFUSE_HOST` | No | Langfuse host (default: cloud.langfuse.com) |

---

## Logs

At runtime, all activity is logged to both stdout and `logs/agent.log`:

```
2026-03-26 10:23:44  INFO  [erp.api]              POST /api/chat | session=default | query='who are my top customers?'
2026-03-26 10:23:44  INFO  [erp.agent.service]    [default] Invoking agent | history_msgs=0
2026-03-26 10:23:45  INFO  [erp.agent.tools]      [TOOL] execute_cypher_query | query='MATCH (c:Customer)...'
2026-03-26 10:23:46  INFO  [erp.agent.tools]      [TOOL] execute_cypher_query done | 310 ms | result_len=284
2026-03-26 10:23:47  INFO  [erp.agent.service]    [default] Agent finished | 3420 ms | tool_steps=1 | response_len=512
2026-03-26 10:23:47  INFO  [erp.api]              POST /api/chat OK | session=default | 3422 ms | response_len=512
```
