# SAP O2C Graph Intelligence System

A full-stack application that ingests SAP Order-to-Cash (O2C) data into a Neo4j graph database and enables natural language querying via an AI-powered chat interface backed by Groq's Llama 3.3 70B model.

---

## Live Demo

> **Backend API:** https://sap-o2c-backend-production.up.railway.app
> **Frontend:** https://graph-based-data-modeling-and-query.vercel.app/

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (React + Vite)                 │
│   GraphView (Cytoscape.js)  │  ChatPanel  │  StatsBar           │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP REST
┌────────────────────▼────────────────────────────────────────────┐
│                     Backend (FastAPI / Python)                   │
│                                                                  │
│   /api/graph      – sampled overview graph (nodes + edges)      │
│   /api/expand     – expand a node's neighbors                   │
│   /api/search     – full-text entity search                     │
│   /api/chat       – NL → Cypher → Execute → NL answer           │
│   /api/stats      – node/relationship counts                    │
│   /api/health     – Neo4j connectivity check                    │
└──────────┬────────────────────────────┬───────────────────────  ┘
           │ Bolt protocol              │ Groq API (HTTPS)
┌──────────▼──────────┐     ┌──────────▼──────────────────────── ┐
│   Neo4j Graph DB    │     │   Groq – Llama 3.3 70B Versatile   │
│   (12 node labels,  │     │   (Cypher generation + NL summary) │
│   11 rel types)     │     └─────────────────────────────────── ┘
└─────────────────────┘
           ▲
           │ ingest.py (one-time)
┌──────────┴──────────┐
│  SAP O2C JSONL Data │
│  (business_partners,│
│   sales_orders, … ) │
└─────────────────────┘
```

### Component Breakdown

**`backend/ingest.py`** — One-time data loader. Reads JSONL files from the `sap-o2c-data/` directory in batches of 500 records and upserts them into Neo4j using `MERGE` statements. Creates unique constraints on all primary keys before ingestion to ensure idempotency.

**`backend/main.py`** — FastAPI REST API. Exposes graph query endpoints with a smart overview strategy: instead of returning all 21k+ nodes on load, it returns a sample (≤80 nodes, ≤150 edges) per label type for performant initial rendering. Node expansion is on-demand.

**`backend/llm.py`** — LLM orchestration layer. Implements a two-stage pipeline: (1) natural language → Cypher, and (2) raw database results → natural language answer. Includes a self-correction loop that retries failed Cypher queries once with the error message fed back to the model.

**`frontend/`** — React + Vite SPA. Uses [Cytoscape.js](https://js.cytoscape.org/) for interactive graph rendering with per-label colour coding and shape differentiation. The chat panel streams AI answers with the generated Cypher visible for transparency.

---

## Database Choice — Neo4j

The SAP O2C process is a deeply relational chain:

```
BusinessPartner → SalesOrder → SalesOrderItem → OutboundDeliveryItem
  ← OutboundDelivery ← BillingDocument → JournalEntry ← Payment
```

A **graph database** is the natural fit for this because:

- **Relationship traversal is first-class** — finding "all payments linked to a customer's sales orders" is a single path query, not a 5-table JOIN.
- **Schema flexibility** — different document types have different properties; Neo4j handles sparse attributes without NULLs everywhere.
- **Visual alignment** — the graph data model maps directly to what users see in the UI.
- **Cypher readability** — LLM-generated Cypher is more legible and less error-prone than equivalent multi-join SQL, which helps with prompt reliability.

**Graph schema** (12 node labels, 11 relationship types):

| Node Label | Key Property | Count (approx) |
|---|---|---|
| BusinessPartner | businessPartner | ~500 |
| SalesOrder | salesOrder | ~5,000 |
| SalesOrderItem | itemId | ~10,000 |
| OutboundDelivery | deliveryDocument | ~4,500 |
| OutboundDeliveryItem | itemId | ~9,000 |
| BillingDocument | billingDocument | ~4,800 |
| BillingDocumentItem | itemId | ~9,600 |
| JournalEntry | journalId | ~5,000 |
| Payment | paymentId | ~3,000 |
| Product | product | ~200 |
| Plant | plant | ~50 |
| Address | addressId | ~500 |

---

## LLM Prompting Strategy

The system uses **Groq's Llama 3.3 70B Versatile** model (via the Groq API) at `temperature=0.1` for deterministic, low-creativity query generation.

### Stage 1 — Natural Language → Cypher

The system prompt is structured in three parts:

1. **Schema injection** — the full node/relationship schema with property names is embedded verbatim, so the model never hallucinates label names or property keys.

2. **Strict output format** — the model is instructed to return only a JSON object `{"cypher": "...", "explanation": "..."}` with no surrounding markdown or prose. A regex-based `extract_json()` fallback strips accidental code fences.

3. **Few-shot examples** — three representative Cypher patterns are included (aggregate count, status filter, broken-flow detection using `OPTIONAL MATCH + WHERE x IS NULL`) to anchor the model to the correct query style.

```
temperature = 0.1   # deterministic, consistent query structure
max_tokens  = 1024  # enough for complex multi-hop Cypher
```

### Stage 2 — Results → Natural Language Answer

After query execution, a separate, lighter prompt sends the raw result rows (capped at 10 for token efficiency) back to the model asking for a 2–4 sentence business analyst summary. This runs at `temperature=0.3` to allow slightly more natural phrasing.

### Self-Correction Loop

If the generated Cypher fails on execution, the error message and original query are fed back to the model in a repair prompt. This handles edge cases like property name typos or incorrect relationship directions without surfacing errors to the user.

### Conversation History

The last 4 conversation turns are prepended to each prompt as `User:/Assistant:` pairs, enabling follow-up questions like "now filter that by currency EUR" without re-stating context.

---

## Guardrails

Multiple layers prevent misuse and ensure data safety:

### 1. LLM-Level — Off-Topic Rejection
The system prompt instructs the model to return `{"cypher": null, "explanation": "..."}` for any question unrelated to the O2C dataset (e.g. general knowledge, coding help, creative writing). The API detects `cypher: null` and returns the explanation as the answer without executing anything.

### 2. Code-Level — Write Operation Blocking
Before any Cypher query reaches Neo4j, it is validated against a keyword blocklist:

```python
BLOCKED_KEYWORDS = ["create", "delete", "set", "merge", "drop", "remove", "detach"]
```

Any query containing these keywords (checked with word-boundary regex to avoid false positives on property names) is rejected with a clear error message.

### 3. Code-Level — Query Start Validation
Queries must begin with `MATCH`, `WITH`, `CALL`, or `OPTIONAL MATCH`. This prevents injection patterns that start with `FOREACH`, `UNWIND` (for writes), or arbitrary clauses.

### 4. Result Size Limits
- All Cypher queries include `LIMIT 25` by default (enforced in the prompt instructions).
- The API response caps returned rows at 50, preventing accidental data dumps.
- The graph overview endpoint samples ≤80 nodes and ≤150 edges to keep the frontend responsive.

### 5. Read-Only Neo4j User (recommended for production)
The application connects with credentials from `.env`. For production, Neo4j should be configured with a read-only user that has no write privileges at the database level as a final defence layer.

---

## Setup Instructions

### Prerequisites

- Python 3.12 (required — `pydantic-core` uses Rust/PyO3 which does not yet support Python 3.14)
- Node.js 18+
- Neo4j 5.x (local, Docker, or AuraDB)
- Groq API key (free tier available at [console.groq.com](https://console.groq.com))

### 1. Clone & configure environment

```bash
git clone <your-repo-url>
cd backend-graphdb
```

Create `backend/.env`:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GROQ_API_KEY=your_groq_api_key
DATA_DIR=../sap-o2c-data
```

### 2. Start Neo4j

Using Docker:

```bash
docker run -d \
  --name neo4j-o2c \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5
```

Or use [Neo4j AuraDB](https://neo4j.com/cloud/platform/aura-graph-database/) (free tier) and update `NEO4J_URI` to the AuraDB connection string.

### 3. Backend setup

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

### 4. Ingest data

```bash
python3 ingest.py
# Expect: ~21,000 nodes and ~35,000 relationships ingested
```

### 5. Start the API

```bash
python3 -m uvicorn main:app --reload --port 8000
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 6. Frontend setup

```bash
cd ../frontend
npm install
npm run dev
# UI available at http://localhost:5173
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Neo4j connectivity check |
| GET | `/api/stats` | Node and relationship counts |
| GET | `/api/graph` | Sampled overview graph for initial render |
| GET | `/api/expand/{node_type}/{node_id}` | Expand neighbors of a specific node |
| GET | `/api/search?q={term}` | Full-text search across entity IDs and names |
| GET | `/api/suggestions` | Pre-built example questions for the UI |
| POST | `/api/chat` | Natural language query → answer + Cypher + data |

### Chat request format

```json
{
  "message": "Which customers have the highest total order value?",
  "history": [
    { "user": "Show cancelled billing documents", "assistant": "Found 42 cancelled..." }
  ]
}
```

### Chat response format

```json
{
  "answer": "The top customer by order value is Acme Corp with $2.4M across 312 sales orders...",
  "cypher": "MATCH (bp:BusinessPartner)-[:PLACED]->(so:SalesOrder) ...",
  "data": [...],
  "total_records": 25,
  "node_ids": ["100001", "100042", ...]
}
```

---

## Project Structure

```
backend-graphdb/
├── backend/
│   ├── main.py          # FastAPI app — REST endpoints
│   ├── llm.py           # Groq integration — NL→Cypher pipeline
│   ├── ingest.py        # One-time Neo4j data loader
│   ├── requirements.txt
│   └── .env             # (not committed) API keys & DB credentials
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root layout
│   │   ├── GraphView.jsx    # Cytoscape.js graph canvas
│   │   ├── ChatPanel.jsx    # AI chat interface
│   │   └── StatsBar.jsx     # Node/edge count display
│   ├── index.html
│   └── package.json
└── README.md
```

---

## Example Queries

These can be typed directly into the chat interface:

- "Which products appear in the most billing documents?"
- "Show sales orders that were delivered but never billed"
- "Trace the full flow for billing document 90504298"
- "Which customers have the highest total order value?"
- "Show billing documents that have been cancelled"
- "Which plants handle the most deliveries?"
- "Find payments and the journal entries they clear"
- "What is the total billed amount by currency?"

---

## Tech Stack

| Layer | Technology |
|---|---|
| Graph Database | Neo4j 5.x |
| Backend API | FastAPI, Python 3.12 |
| LLM | Groq — Llama 3.3 70B Versatile |
| Graph Visualization | Cytoscape.js |
| Frontend | React 18, Vite |
| DB Driver | neo4j-python-driver 5.20 |
