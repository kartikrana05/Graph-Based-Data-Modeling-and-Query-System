"""
Neo4j Ingestion Script for SAP O2C Dataset
Reads JSONL files and loads nodes + relationships into Neo4j
"""

import os
import json
import glob
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DATA_DIR       = os.getenv("DATA_DIR", "../sap-o2c-data")   # adjust to your JSONL root

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def read_jsonl(folder_name):
    path = os.path.join(DATA_DIR, folder_name, "*.jsonl")
    records = []
    for file in glob.glob(path):
        with open(file) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    print(f"  Loaded {len(records):,} records from {folder_name}")
    return records


def run_batch(session, query, records, batch_size=500):
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        session.run(query, {"batch": batch})


# ─────────────────────────────────────────────
# Schema constraints (run once)
# ─────────────────────────────────────────────

def create_constraints(session):
    print("\n[1/10] Creating constraints & indexes...")
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:BusinessPartner)  REQUIRE n.businessPartner IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:SalesOrder)        REQUIRE n.salesOrder IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:SalesOrderItem)    REQUIRE n.itemId IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:OutboundDelivery)  REQUIRE n.deliveryDocument IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:OutboundDeliveryItem) REQUIRE n.itemId IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:BillingDocument)   REQUIRE n.billingDocument IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:BillingDocumentItem) REQUIRE n.itemId IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:JournalEntry)      REQUIRE n.journalId IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Payment)           REQUIRE n.paymentId IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Product)           REQUIRE n.product IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Plant)             REQUIRE n.plant IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Address)           REQUIRE n.addressId IS UNIQUE",
    ]
    for c in constraints:
        session.run(c)
    print("  Done.")


# ─────────────────────────────────────────────
# Node ingestion
# ─────────────────────────────────────────────

def ingest_business_partners(session):
    print("\n[2/10] Ingesting BusinessPartners...")
    records = read_jsonl("business_partners")
    query = """
    UNWIND $batch AS r
    MERGE (bp:BusinessPartner {businessPartner: r.businessPartner})
    SET bp.customer                 = r.customer,
        bp.businessPartnerFullName  = r.businessPartnerFullName,
        bp.businessPartnerName      = r.businessPartnerName,
        bp.industry                 = r.industry,
        bp.businessPartnerCategory  = r.businessPartnerCategory,
        bp.businessPartnerIsBlocked = r.businessPartnerIsBlocked,
        bp.creationDate             = r.creationDate
    """
    run_batch(session, query, records)

    # Addresses
    addr_records = read_jsonl("business_partner_addresses")
    addr_query = """
    UNWIND $batch AS r
    MERGE (a:Address {addressId: r.addressId})
    SET a.businessPartner = r.businessPartner,
        a.cityName        = r.cityName,
        a.country         = r.country,
        a.region          = r.region,
        a.postalCode      = r.postalCode,
        a.streetName      = r.streetName,
        a.transportZone   = r.transportZone
    WITH a, r
    MATCH (bp:BusinessPartner {businessPartner: r.businessPartner})
    MERGE (bp)-[:HAS_ADDRESS]->(a)
    """
    run_batch(session, addr_query, addr_records)
    print("  Done.")


def ingest_products(session):
    print("\n[3/10] Ingesting Products...")
    records = read_jsonl("products")
    query = """
    UNWIND $batch AS r
    MERGE (p:Product {product: r.product})
    SET p.productType    = r.productType,
        p.productGroup   = r.productGroup,
        p.grossWeight    = r.grossWeight,
        p.weightUnit     = r.weightUnit,
        p.baseUnit       = r.baseUnit,
        p.division       = r.division,
        p.industrySector = r.industrySector,
        p.creationDate   = r.creationDate
    """
    run_batch(session, query, records)

    # Product descriptions (merge as property on Product node)
    desc_records = read_jsonl("product_descriptions")
    desc_query = """
    UNWIND $batch AS r
    MATCH (p:Product {product: r.product})
    WHERE r.language = 'EN'
    SET p.productDescription = r.productDescription
    """
    run_batch(session, desc_query, desc_records)
    print("  Done.")


def ingest_plants(session):
    print("\n[4/10] Ingesting Plants...")
    records = read_jsonl("plants")
    query = """
    UNWIND $batch AS r
    MERGE (pl:Plant {plant: r.plant})
    SET pl.plantName             = r.plantName,
        pl.valuationArea         = r.valuationArea,
        pl.salesOrganization     = r.salesOrganization,
        pl.distributionChannel   = r.distributionChannel,
        pl.division              = r.division
    """
    run_batch(session, query, records)
    print("  Done.")


def ingest_sales_orders(session):
    print("\n[5/10] Ingesting SalesOrders + Items...")
    headers = read_jsonl("sales_order_headers")
    header_query = """
    UNWIND $batch AS r
    MERGE (so:SalesOrder {salesOrder: r.salesOrder})
    SET so.salesOrderType               = r.salesOrderType,
        so.soldToParty                  = r.soldToParty,
        so.totalNetAmount               = toFloat(r.totalNetAmount),
        so.transactionCurrency          = r.transactionCurrency,
        so.overallDeliveryStatus        = r.overallDeliveryStatus,
        so.overallOrdReltdBillgStatus   = r.overallOrdReltdBillgStatus,
        so.creationDate                 = r.creationDate,
        so.requestedDeliveryDate        = r.requestedDeliveryDate,
        so.salesOrganization            = r.salesOrganization,
        so.customerPaymentTerms         = r.customerPaymentTerms,
        so.headerBillingBlockReason     = r.headerBillingBlockReason,
        so.deliveryBlockReason          = r.deliveryBlockReason
    WITH so, r
    MATCH (bp:BusinessPartner {customer: r.soldToParty})
    MERGE (bp)-[:PLACED]->(so)
    """
    run_batch(session, header_query, headers)

    items = read_jsonl("sales_order_items")
    item_query = """
    UNWIND $batch AS r
    MERGE (soi:SalesOrderItem {itemId: r.salesOrder + '-' + r.salesOrderItem})
    SET soi.salesOrder              = r.salesOrder,
        soi.salesOrderItem          = r.salesOrderItem,
        soi.material                = r.material,
        soi.requestedQuantity       = toFloat(r.requestedQuantity),
        soi.requestedQuantityUnit   = r.requestedQuantityUnit,
        soi.netAmount               = toFloat(r.netAmount),
        soi.productionPlant         = r.productionPlant,
        soi.storageLocation         = r.storageLocation,
        soi.salesDocumentRjcnReason = r.salesDocumentRjcnReason
    WITH soi, r
    MATCH (so:SalesOrder {salesOrder: r.salesOrder})
    MERGE (so)-[:HAS_ITEM]->(soi)
    WITH soi, r
    MATCH (p:Product {product: r.material})
    MERGE (soi)-[:REFERENCES]->(p)
    """
    run_batch(session, item_query, items)
    print("  Done.")


def ingest_deliveries(session):
    print("\n[6/10] Ingesting OutboundDeliveries + Items...")
    headers = read_jsonl("outbound_delivery_headers")
    header_query = """
    UNWIND $batch AS r
    MERGE (od:OutboundDelivery {deliveryDocument: r.deliveryDocument})
    SET od.shippingPoint                = r.shippingPoint,
        od.creationDate                 = r.creationDate,
        od.actualGoodsMovementDate      = r.actualGoodsMovementDate,
        od.overallGoodsMovementStatus   = r.overallGoodsMovementStatus,
        od.overallPickingStatus         = r.overallPickingStatus,
        od.overallProofOfDeliveryStatus = r.overallProofOfDeliveryStatus,
        od.headerBillingBlockReason     = r.headerBillingBlockReason,
        od.deliveryBlockReason          = r.deliveryBlockReason
    """
    run_batch(session, header_query, headers)

    items = read_jsonl("outbound_delivery_items")
    item_query = """
    UNWIND $batch AS r
    MERGE (doi:OutboundDeliveryItem {itemId: r.deliveryDocument + '-' + r.deliveryDocumentItem})
    SET doi.deliveryDocument        = r.deliveryDocument,
        doi.deliveryDocumentItem    = r.deliveryDocumentItem,
        doi.plant                   = r.plant,
        doi.actualDeliveryQuantity  = toFloat(r.actualDeliveryQuantity),
        doi.deliveryQuantityUnit    = r.deliveryQuantityUnit,
        doi.referenceSdDocument     = r.referenceSdDocument,
        doi.referenceSdDocumentItem = r.referenceSdDocumentItem,
        doi.storageLocation         = r.storageLocation
    WITH doi, r
    // Link to Delivery Header
    MATCH (od:OutboundDelivery {deliveryDocument: r.deliveryDocument})
    MERGE (od)-[:HAS_ITEM]->(doi)
    WITH doi, r
    // Link to SalesOrderItem
    MATCH (soi:SalesOrderItem {itemId: r.referenceSdDocument + '-' + r.referenceSdDocumentItem})
    MERGE (soi)-[:DELIVERED_AS]->(doi)
    WITH doi, r
    // Link to Plant
    MATCH (pl:Plant {plant: r.plant})
    MERGE (doi)-[:SHIPPED_FROM]->(pl)
    """
    run_batch(session, item_query, items)
    print("  Done.")


def ingest_billing_documents(session):
    print("\n[7/10] Ingesting BillingDocuments + Items...")
    headers = read_jsonl("billing_document_headers")
    header_query = """
    UNWIND $batch AS r
    MERGE (bd:BillingDocument {billingDocument: r.billingDocument})
    SET bd.billingDocumentType        = r.billingDocumentType,
        bd.totalNetAmount             = toFloat(r.totalNetAmount),
        bd.transactionCurrency        = r.transactionCurrency,
        bd.companyCode                = r.companyCode,
        bd.fiscalYear                 = r.fiscalYear,
        bd.accountingDocument         = r.accountingDocument,
        bd.soldToParty                = r.soldToParty,
        bd.billingDocumentDate        = r.billingDocumentDate,
        bd.creationDate               = r.creationDate,
        bd.billingDocumentIsCancelled = r.billingDocumentIsCancelled,
        bd.cancelledBillingDocument   = r.cancelledBillingDocument
    """
    run_batch(session, header_query, headers)

    items = read_jsonl("billing_document_items")
    item_query = """
    UNWIND $batch AS r
    MERGE (bdi:BillingDocumentItem {itemId: r.billingDocument + '-' + r.billingDocumentItem})
    SET bdi.billingDocument     = r.billingDocument,
        bdi.billingDocumentItem = r.billingDocumentItem,
        bdi.material            = r.material,
        bdi.billingQuantity     = toFloat(r.billingQuantity),
        bdi.netAmount           = toFloat(r.netAmount),
        bdi.transactionCurrency = r.transactionCurrency,
        bdi.referenceSdDocument = r.referenceSdDocument
    WITH bdi, r
    // Link item to header
    MATCH (bd:BillingDocument {billingDocument: r.billingDocument})
    MERGE (bd)-[:HAS_ITEM]->(bdi)
    WITH bdi, r, bd
    // Link BillingDocument to OutboundDelivery (via referenceSdDocument = deliveryDocument)
    MATCH (od:OutboundDelivery {deliveryDocument: r.referenceSdDocument})
    MERGE (bd)-[:BILLS]->(od)
    """
    run_batch(session, item_query, items)
    print("  Done.")


def ingest_journal_entries(session):
    print("\n[8/10] Ingesting JournalEntries...")
    records = read_jsonl("journal_entry_items_accounts_receivable")
    query = """
    UNWIND $batch AS r
    MERGE (je:JournalEntry {journalId: r.accountingDocument + '-' + r.accountingDocumentItem + '-' + r.fiscalYear})
    SET je.accountingDocument         = r.accountingDocument,
        je.accountingDocumentItem     = r.accountingDocumentItem,
        je.fiscalYear                 = r.fiscalYear,
        je.companyCode                = r.companyCode,
        je.glAccount                  = r.glAccount,
        je.referenceDocument          = r.referenceDocument,
        je.amountInTransactionCurrency = toFloat(r.amountInTransactionCurrency),
        je.transactionCurrency        = r.transactionCurrency,
        je.postingDate                = r.postingDate,
        je.customer                   = r.customer,
        je.clearingDate               = r.clearingDate,
        je.clearingAccountingDocument = r.clearingAccountingDocument,
        je.accountingDocumentType     = r.accountingDocumentType
    WITH je, r
    // Link to BillingDocument via accountingDocument
    MATCH (bd:BillingDocument {accountingDocument: r.accountingDocument})
    MERGE (bd)-[:GENERATES]->(je)
    """
    run_batch(session, query, records)
    print("  Done.")


def ingest_payments(session):
    print("\n[9/10] Ingesting Payments...")
    records = read_jsonl("payments_accounts_receivable")
    query = """
    UNWIND $batch AS r
    MERGE (pay:Payment {paymentId: r.accountingDocument + '-' + r.accountingDocumentItem + '-' + r.fiscalYear})
    SET pay.accountingDocument              = r.accountingDocument,
        pay.accountingDocumentItem          = r.accountingDocumentItem,
        pay.fiscalYear                      = r.fiscalYear,
        pay.companyCode                     = r.companyCode,
        pay.amountInTransactionCurrency     = toFloat(r.amountInTransactionCurrency),
        pay.transactionCurrency             = r.transactionCurrency,
        pay.clearingAccountingDocument      = r.clearingAccountingDocument,
        pay.clearingDocFiscalYear           = r.clearingDocFiscalYear,
        pay.customer                        = r.customer,
        pay.postingDate                     = r.postingDate,
        pay.glAccount                       = r.glAccount
    WITH pay, r
    // Link Payment to JournalEntry it clears
    MATCH (je:JournalEntry {accountingDocument: r.clearingAccountingDocument})
    MERGE (pay)-[:CLEARS]->(je)
    """
    run_batch(session, query, records)
    print("  Done.")


def ingest_cancellations(session):
    print("\n[10/10] Ingesting BillingDocument Cancellations...")
    records = read_jsonl("billing_document_cancellations")
    query = """
    UNWIND $batch AS r
    MERGE (bc:BillingDocument {billingDocument: r.billingDocument})
    SET bc.billingDocumentType        = r.billingDocumentType,
        bc.totalNetAmount             = toFloat(r.totalNetAmount),
        bc.companyCode                = r.companyCode,
        bc.fiscalYear                 = r.fiscalYear,
        bc.accountingDocument         = r.accountingDocument,
        bc.soldToParty                = r.soldToParty,
        bc.billingDocumentIsCancelled = r.billingDocumentIsCancelled,
        bc.cancelledBillingDocument   = r.cancelledBillingDocument,
        bc.isCancellation             = true
    WITH bc, r
    // Link cancellation to the original billing doc it cancels
    MATCH (orig:BillingDocument {billingDocument: r.cancelledBillingDocument})
    MERGE (bc)-[:CANCELS]->(orig)
    """
    run_batch(session, query, records)
    print("  Done.")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("SAP O2C Neo4j Ingestion")
    print("=" * 50)
    print(f"Connecting to: {NEO4J_URI}")

    with driver.session() as session:
        create_constraints(session)
        ingest_business_partners(session)
        ingest_products(session)
        ingest_plants(session)
        ingest_sales_orders(session)
        ingest_deliveries(session)
        ingest_billing_documents(session)
        ingest_journal_entries(session)
        ingest_payments(session)
        ingest_cancellations(session)

    print("\n✅ Ingestion complete!")

    # Print summary stats
    with driver.session() as session:
        print("\n📊 Graph Summary:")
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
        """)
        for r in result:
            print(f"  {r['label']:<30} {r['count']:>6} nodes")

        result = session.run("MATCH ()-[r]->() RETURN count(r) AS total")
        print(f"\n  Total Relationships: {result.single()['total']:,}")

    driver.close()


if __name__ == "__main__":
    main()
