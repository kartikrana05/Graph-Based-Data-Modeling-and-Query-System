"""
LLM Integration — Groq (Llama 3.3 70B)
Natural language → Cypher → Execute → Natural language response
"""

import os
import json
import re
from groq import Groq
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ─────────────────────────────────────────────
# Neo4j Schema for LLM context
# ─────────────────────────────────────────────

SCHEMA = """
You have access to a Neo4j graph database representing SAP Order-to-Cash (O2C) data.

NODE LABELS AND KEY PROPERTIES:
- BusinessPartner: businessPartner, customer, businessPartnerFullName, industry, businessPartnerIsBlocked
- SalesOrder: salesOrder, soldToParty, totalNetAmount, transactionCurrency, overallDeliveryStatus, overallOrdReltdBillgStatus, creationDate, salesOrderType, customerPaymentTerms
- SalesOrderItem: itemId (=salesOrder+'-'+salesOrderItem), salesOrder, salesOrderItem, material, requestedQuantity, netAmount, productionPlant, salesDocumentRjcnReason
- OutboundDelivery: deliveryDocument, shippingPoint, actualGoodsMovementDate, overallGoodsMovementStatus, overallPickingStatus, creationDate
- OutboundDeliveryItem: itemId, deliveryDocument, plant, actualDeliveryQuantity, referenceSdDocument, referenceSdDocumentItem
- BillingDocument: billingDocument, billingDocumentType, totalNetAmount, transactionCurrency, companyCode, fiscalYear, accountingDocument, soldToParty, billingDocumentDate, billingDocumentIsCancelled, cancelledBillingDocument, isCancellation
- BillingDocumentItem: itemId, billingDocument, material, billingQuantity, netAmount, referenceSdDocument
- JournalEntry: journalId, accountingDocument, fiscalYear, companyCode, glAccount, amountInTransactionCurrency, postingDate, customer, clearingDate, referenceDocument
- Payment: paymentId, accountingDocument, fiscalYear, companyCode, amountInTransactionCurrency, transactionCurrency, clearingAccountingDocument, customer, postingDate
- Product: product, productDescription, productType, productGroup, grossWeight, baseUnit, division
- Plant: plant, plantName, salesOrganization, distributionChannel
- Address: addressId, cityName, country, region, postalCode, streetName

RELATIONSHIPS (direction matters):
(:BusinessPartner)-[:PLACED]->(:SalesOrder)
(:BusinessPartner)-[:HAS_ADDRESS]->(:Address)
(:SalesOrder)-[:HAS_ITEM]->(:SalesOrderItem)
(:SalesOrderItem)-[:REFERENCES]->(:Product)
(:SalesOrderItem)-[:DELIVERED_AS]->(:OutboundDeliveryItem)
(:OutboundDelivery)-[:HAS_ITEM]->(:OutboundDeliveryItem)
(:OutboundDeliveryItem)-[:SHIPPED_FROM]->(:Plant)
(:BillingDocument)-[:BILLS]->(:OutboundDelivery)
(:BillingDocument)-[:HAS_ITEM]->(:BillingDocumentItem)
(:BillingDocument)-[:GENERATES]->(:JournalEntry)
(:BillingDocument)-[:CANCELS]->(:BillingDocument)   [cancellation doc cancels original]
(:Payment)-[:CLEARS]->(:JournalEntry)

FULL O2C CHAIN:
BusinessPartner → PLACED → SalesOrder → HAS_ITEM → SalesOrderItem → DELIVERED_AS → OutboundDeliveryItem ← HAS_ITEM ← OutboundDelivery ← BILLS ← BillingDocument → GENERATES → JournalEntry ← CLEARS ← Payment
"""

SYSTEM_PROMPT = f"""
You are a Cypher query expert for a Neo4j Order-to-Cash (O2C) database.
Your ONLY job is to answer questions about this specific SAP O2C dataset.

{SCHEMA}

INSTRUCTIONS:
1. When the user asks a question about the O2C data, generate a valid Cypher query.
2. Return ONLY a valid JSON object — no markdown, no explanation outside the JSON.
3. Format:
   {{"cypher": "MATCH ...", "explanation": "Brief description of what the query does"}}

4. If the question is NOT about the O2C dataset (e.g. general knowledge, weather, coding help, creative writing, math problems, etc.):
   {{"cypher": null, "explanation": "This system is designed to answer questions related to the SAP O2C dataset only. Please ask about sales orders, deliveries, billing documents, payments, products, customers, or related business flows."}}

CYPHER RULES:
- Always use LIMIT (default 25 unless user asks for all)
- Only use MATCH, OPTIONAL MATCH, WITH, WHERE, RETURN, ORDER BY, LIMIT, COUNT, COLLECT, DISTINCT
- NEVER use CREATE, DELETE, SET, MERGE, DROP, REMOVE
- Use toFloat() for numeric comparisons on amount fields
- When checking for "broken flows", use OPTIONAL MATCH + WHERE x IS NULL pattern
- For "trace full flow" queries, use path variables: MATCH path = (n)-[*]->(m)
- Property access uses dot notation: n.salesOrder, not n["salesOrder"]
- String matching: use toLower() + CONTAINS for fuzzy search

EXAMPLE QUERIES:
Q: "Which products appear in the most billing documents?"
A: {{"cypher": "MATCH (bdi:BillingDocumentItem) RETURN bdi.material AS product, count(DISTINCT bdi.billingDocument) AS billingCount ORDER BY billingCount DESC LIMIT 10", "explanation": "Counts distinct billing documents per product material"}}

Q: "Show sales orders delivered but not billed"
A: {{"cypher": "MATCH (so:SalesOrder)-[:HAS_ITEM]->(soi:SalesOrderItem)-[:DELIVERED_AS]->(doi:OutboundDeliveryItem)<-[:HAS_ITEM]-(od:OutboundDelivery) WHERE NOT (od)<-[:BILLS]-(:BillingDocument) RETURN DISTINCT so.salesOrder, so.totalNetAmount, so.creationDate LIMIT 25", "explanation": "Finds sales orders with deliveries but no billing document"}}
"""


# ─────────────────────────────────────────────
# Guardrails
# ─────────────────────────────────────────────

BLOCKED_KEYWORDS = ["create", "delete", "set", "merge", "drop", "remove", "detach"]
ALLOWED_NODE_LABELS = {
    "businesspartner", "salesorder", "salesorderitem",
    "outbounddelivery", "outbounddeliveryitem",
    "billingdocument", "billingdocumentitem",
    "journalentry", "payment", "product", "plant", "address"
}

def validate_cypher(cypher: str) -> tuple[bool, str]:
    """Returns (is_valid, reason)"""
    lower = cypher.lower()

    # Block write operations
    for kw in BLOCKED_KEYWORDS:
        if re.search(rf'\b{kw}\b', lower):
            return False, f"Write operation '{kw}' is not allowed"

    # Must start with MATCH or WITH or CALL
    stripped = lower.strip()
    if not (stripped.startswith("match") or stripped.startswith("with") or
            stripped.startswith("call") or stripped.startswith("optional")):
        return False, "Query must start with MATCH"

    return True, "ok"


# ─────────────────────────────────────────────
# Core chat function
# ─────────────────────────────────────────────

def execute_cypher(cypher: str) -> list:
    with driver.session() as session:
        result = session.run(cypher)
        return result.data()


def extract_json(text: str) -> dict:
    """Robustly extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object anywhere in the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from: {text[:200]}")


def call_llm(prompt: str, temperature: float = 0.1, max_tokens: int = 1024) -> str:
    """Call Groq LLM and return raw text response."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def chat(user_message: str, conversation_history: list = None) -> dict:
    """
    Main chat function.
    Returns: { answer, cypher, data, node_ids }
    """
    # Build conversation context if history provided
    history_text = ""
    if conversation_history:
        for turn in conversation_history[-4:]:
            history_text += f"\nUser: {turn['user']}\nAssistant: {turn['assistant']}\n"

    prompt = f"{SYSTEM_PROMPT}\n{history_text}\nUser: {user_message}"

    try:
        raw = call_llm(prompt, temperature=0.1, max_tokens=1024)
        print(f"[LLM RAW RESPONSE]: {raw[:300]}")
        parsed = extract_json(raw)
    except Exception as e:
        print(f"[LLM ERROR]: {e}")
        return {
            "answer": "I had trouble generating a query. Please rephrase your question.",
            "cypher": None,
            "data": [],
            "node_ids": [],
            "error": str(e)
        }

    cypher = parsed.get("cypher")
    explanation = parsed.get("explanation", "")

    # Off-topic guardrail
    if not cypher:
        return {
            "answer": explanation,
            "cypher": None,
            "data": [],
            "node_ids": []
        }

    # Safety validation
    is_valid, reason = validate_cypher(cypher)
    if not is_valid:
        return {
            "answer": f"Query blocked for safety: {reason}",
            "cypher": cypher,
            "data": [],
            "node_ids": []
        }

    # Execute
    try:
        data = execute_cypher(cypher)
    except Exception as e:
        # Try to self-correct once
        fix_prompt = f"""
The following Cypher query failed with error: {str(e)}
Query: {cypher}
Schema: {SCHEMA}
Please return a corrected JSON with fixed Cypher only.
Format: {{"cypher": "MATCH ...", "explanation": "..."}}
"""
        try:
            fix_raw = call_llm(fix_prompt, temperature=0.1, max_tokens=512)
            fix_parsed = extract_json(fix_raw)
            cypher = fix_parsed.get("cypher", cypher)
            data = execute_cypher(cypher)
        except Exception as e2:
            return {
                "answer": f"Query execution failed: {str(e)}",
                "cypher": cypher,
                "data": [],
                "node_ids": []
            }

    # Generate natural language answer from results
    if not data:
        answer = "No results found for your query."
    else:
        summary_prompt = f"""
The user asked: "{user_message}"
The database returned {len(data)} records: {json.dumps(data[:10], indent=2, default=str)}
{"(showing first 10 of " + str(len(data)) + " total)" if len(data) > 10 else ""}

Write a clear, concise answer (2-4 sentences) summarizing these results.
Be specific — include numbers, IDs, and amounts where relevant.
Do not mention Cypher or databases. Speak naturally as a business analyst.
"""
        answer = call_llm(summary_prompt, temperature=0.3, max_tokens=256)

    # Extract node IDs for frontend highlighting
    node_ids = extract_node_ids(data)

    return {
        "answer": answer,
        "cypher": cypher,
        "data": data[:50],
        "total_records": len(data),
        "node_ids": node_ids
    }


def extract_node_ids(data: list) -> list:
    """Extract any IDs from results for graph highlighting"""
    ids = []
    id_fields = [
        "salesOrder", "deliveryDocument", "billingDocument",
        "businessPartner", "product", "plant", "paymentId", "journalId"
    ]
    for row in data:
        for field in id_fields:
            if field in row and row[field]:
                ids.append(str(row[field]))
    return list(set(ids))