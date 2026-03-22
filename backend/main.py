"""
FastAPI Backend — SAP O2C Graph Query System
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv
from llm import chat, driver as llm_driver

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

app = FastAPI(title="SAP O2C Graph API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list = []


class ExpandRequest(BaseModel):
    node_id: str
    node_type: str


# ─────────────────────────────────────────────
# Node color/type config (for frontend)
# ─────────────────────────────────────────────

NODE_STYLES = {
    "BusinessPartner":     {"color": "#9B59B6", "shape": "ellipse"},
    "SalesOrder":          {"color": "#2E86AB", "shape": "roundrectangle"},
    "SalesOrderItem":      {"color": "#74B3CE", "shape": "roundrectangle"},
    "OutboundDelivery":    {"color": "#27AE60", "shape": "roundrectangle"},
    "OutboundDeliveryItem":{"color": "#82E0AA", "shape": "roundrectangle"},
    "BillingDocument":     {"color": "#E67E22", "shape": "roundrectangle"},
    "BillingDocumentItem": {"color": "#F0B27A", "shape": "roundrectangle"},
    "JournalEntry":        {"color": "#E74C3C", "shape": "roundrectangle"},
    "Payment":             {"color": "#C0392B", "shape": "ellipse"},
    "Product":             {"color": "#F39C12", "shape": "diamond"},
    "Plant":               {"color": "#1ABC9C", "shape": "pentagon"},
    "Address":             {"color": "#95A5A6", "shape": "ellipse"},
}

def format_node(label, props):
    style = NODE_STYLES.get(label, {"color": "#BDC3C7", "shape": "ellipse"})
    node_id = (
        props.get("salesOrder") or props.get("deliveryDocument") or
        props.get("billingDocument") or props.get("businessPartner") or
        props.get("product") or props.get("plant") or
        props.get("journalId") or props.get("paymentId") or
        props.get("addressId") or props.get("itemId") or
        props.get("addressId") or str(id(props))
    )
    display_label = (
        props.get("businessPartnerFullName") or
        props.get("productDescription") or
        props.get("plantName") or
        props.get("salesOrder") or
        props.get("deliveryDocument") or
        props.get("billingDocument") or
        props.get("product") or
        node_id
    )
    return {
        "data": {
            "id": f"{label}_{node_id}",
            "label": f"{label}\n{display_label}",
            "type": label,
            "color": style["color"],
            "shape": style["shape"],
            "props": props
        }
    }

def format_edge(src_id, tgt_id, rel_type):
    return {
        "data": {
            "id": f"{src_id}__{rel_type}__{tgt_id}",
            "source": src_id,
            "target": tgt_id,
            "label": rel_type
        }
    }


# ─────────────────────────────────────────────
# Graph Overview Endpoint
# ─────────────────────────────────────────────

@app.get("/api/graph")
def get_graph_overview():
    """
    Returns a summary graph: one node per label type + relationship counts.
    Used for the initial graph view (avoids rendering 21k nodes at once).
    """
    with driver.session() as session:
        # Node counts per label
        label_counts = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
        """).data()

        # Relationship counts per type
        rel_counts = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS rel, count(r) AS count
        """).data()

        # Sample nodes — a few of each type for initial display
        sample_nodes = session.run("""
            MATCH (n)
            WITH labels(n)[0] AS label, collect(n)[..3] AS samples
            UNWIND samples AS n
            RETURN labels(n)[0] AS label, properties(n) AS props
            LIMIT 80
        """).data()

        # Sample relationships between sampled nodes
        sample_rels = session.run("""
            MATCH (a)-[r]->(b)
            RETURN labels(a)[0] AS srcLabel,
                   labels(b)[0] AS tgtLabel,
                   type(r) AS relType,
                   properties(a) AS srcProps,
                   properties(b) AS tgtProps
            LIMIT 150
        """).data()

    nodes = {}
    edges = []

    for row in sample_nodes:
        n = format_node(row["label"], row["props"])
        nodes[n["data"]["id"]] = n

    for row in sample_rels:
        src = format_node(row["srcLabel"], row["srcProps"])
        tgt = format_node(row["tgtLabel"], row["tgtProps"])
        if src["data"]["id"] in nodes and tgt["data"]["id"] in nodes:
            edges.append(format_edge(src["data"]["id"], tgt["data"]["id"], row["relType"]))

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "nodeCounts": label_counts,
            "relCounts": rel_counts
        }
    }


# ─────────────────────────────────────────────
# Expand Node Endpoint
# ─────────────────────────────────────────────

@app.get("/api/expand/{node_type}/{node_id}")
def expand_node(node_type: str, node_id: str):
    """Returns immediate neighbors of a node."""

    LABEL_KEY_MAP = {
        "SalesOrder":           "salesOrder",
        "OutboundDelivery":     "deliveryDocument",
        "BillingDocument":      "billingDocument",
        "BusinessPartner":      "businessPartner",
        "Product":              "product",
        "Plant":                "plant",
        "SalesOrderItem":       "itemId",
        "OutboundDeliveryItem": "itemId",
        "BillingDocumentItem":  "itemId",
        "JournalEntry":         "journalId",
        "Payment":              "paymentId",
        "Address":              "addressId",
    }

    key = LABEL_KEY_MAP.get(node_type, "id")

    with driver.session() as session:
        result = session.run(f"""
            MATCH (n:{node_type} {{{key}: $node_id}})-[r]-(neighbor)
            RETURN n, type(r) AS relType, neighbor,
                   labels(neighbor)[0] AS neighborLabel,
                   startNode(r) = n AS isOutgoing
            LIMIT 50
        """, node_id=node_id)
        rows = result.data()

    nodes = {}
    edges = []

    for row in rows:
        neighbor_label = row["neighborLabel"]
        neighbor_props = dict(row["neighbor"])
        neighbor_node = format_node(neighbor_label, neighbor_props)
        nodes[neighbor_node["data"]["id"]] = neighbor_node

        src_node = format_node(node_type, dict(row["n"]))
        nodes[src_node["data"]["id"]] = src_node

        if row["isOutgoing"]:
            edges.append(format_edge(src_node["data"]["id"], neighbor_node["data"]["id"], row["relType"]))
        else:
            edges.append(format_edge(neighbor_node["data"]["id"], src_node["data"]["id"], row["relType"]))

    return {"nodes": list(nodes.values()), "edges": edges}


# ─────────────────────────────────────────────
# Search Nodes Endpoint
# ─────────────────────────────────────────────

@app.get("/api/search")
def search_nodes(q: str, limit: int = 20):
    """Full-text search across key entity IDs and names."""
    with driver.session() as session:
        result = session.run("""
            MATCH (n)
            WHERE toLower(toString(n.salesOrder)) CONTAINS toLower($q)
               OR toLower(toString(n.billingDocument)) CONTAINS toLower($q)
               OR toLower(toString(n.deliveryDocument)) CONTAINS toLower($q)
               OR toLower(toString(n.businessPartnerFullName)) CONTAINS toLower($q)
               OR toLower(toString(n.productDescription)) CONTAINS toLower($q)
               OR toLower(toString(n.product)) CONTAINS toLower($q)
               OR toLower(toString(n.plant)) CONTAINS toLower($q)
            RETURN labels(n)[0] AS label, properties(n) AS props
            LIMIT $limit
        """, q=q, limit=limit)
        rows = result.data()

    nodes = [format_node(r["label"], r["props"]) for r in rows]
    return {"nodes": nodes, "count": len(nodes)}


# ─────────────────────────────────────────────
# Chat Endpoint
# ─────────────────────────────────────────────

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    """
    Natural language → Cypher → Execute → Natural language answer
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = chat(req.message, req.history)
    return result


# ─────────────────────────────────────────────
# Health + Stats
# ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return {"status": "ok", "neo4j": "connected"}
    except Exception as e:
        return {"status": "error", "neo4j": str(e)}


@app.get("/api/stats")
def stats():
    with driver.session() as session:
        node_counts = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
        """).data()
        rel_counts = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            ORDER BY count DESC
        """).data()
    return {"nodes": node_counts, "relationships": rel_counts}


# ─────────────────────────────────────────────
# Suggested queries for the UI
# ─────────────────────────────────────────────

@app.get("/api/suggestions")
def suggestions():
    return {"suggestions": [
        "Which products appear in the most billing documents?",
        "Show me all sales orders with their delivery status",
        "Find sales orders that were delivered but never billed",
        "Trace the full flow for billing document 90504298",
        "Which customers have the highest total order value?",
        "Show billing documents that have been cancelled",
        "Which plants handle the most deliveries?",
        "Find payments and the journal entries they clear",
        "Show sales orders where items were rejected",
        "What is the total billed amount by currency?",
    ]}
