"""
Kuzu graph database store.
Loads the serialized graph.json into Kùzu for Cypher-powered querying.

Usage:
    python -m graph_rag.kuzu_store          # ETL from graph.json → Kuzu
    python -m graph_rag.kuzu_store --verify  # ETL + run verification queries
"""
import json
import shutil
from pathlib import Path

import kuzu

from .config import OUTPUT_DIR

# ─── Paths ────────────────────────────────────────────────────────────────────
KUZU_DB_DIR = OUTPUT_DIR / "kuzu_db"
GRAPH_JSON_PATH = OUTPUT_DIR / "graph.json"


# ─── Schema Definitions ──────────────────────────────────────────────────────
# Each node table: (table_name, {property_name: kuzu_type})
# All properties nullable by default in Kuzu.

NODE_SCHEMAS = {
    "Customer": {
        "node_id": "STRING",
        "name": "STRING",
        "category": "STRING",
        "grouping": "STRING",
        "is_blocked": "STRING",
        "is_archived": "STRING",
        "created_date": "STRING",
        "city": "STRING",
        "region": "STRING",
        "country": "STRING",
        "postal_code": "STRING",
        "street": "STRING",
        "timezone": "STRING",
        "reconciliation_account": "STRING",
        "company_payment_terms": "STRING",
        "account_group": "STRING",
        "is_deletion_flagged": "STRING",
        "payment_block_reason": "STRING",
        "currency": "STRING",
        "payment_terms": "STRING",
        "distribution_channel": "STRING",
        "division": "STRING",
        "shipping_condition": "STRING",
        "incoterms": "STRING",
        "incoterms_location": "STRING",
        "delivery_priority": "STRING",
        "sales_area_count": "STRING",
        "total_orders": "STRING",
        "total_billed_amount": "STRING",
        "billing_doc_count": "STRING",
        "outstanding_amount": "STRING",
        "avg_days_to_pay": "STRING",
    },
    "Product": {
        "node_id": "STRING",
        "entity_id": "STRING",
        "doc_type": "STRING",
        "product_group": "STRING",
        "base_unit": "STRING",
        "net_weight": "STRING",
        "gross_weight": "STRING",
        "weight_unit": "STRING",
        "division": "STRING",
        "old_id": "STRING",
        "is_deleted": "STRING",
        "created_date": "STRING",
        "industry_sector": "STRING",
        "description": "STRING",
        "order_count": "STRING",
        "total_ordered_qty": "STRING",
        "plant_count": "STRING",
    },
    "Plant": {
        "node_id": "STRING",
        "name": "STRING",
        "sales_organization": "STRING",
        "factory_calendar": "STRING",
        "distribution_channel": "STRING",
        "division": "STRING",
        "language": "STRING",
        "is_archived": "STRING",
        "order_count": "STRING",
        "product_count": "STRING",
    },
    "SalesOrder": {
        "node_id": "STRING",
        "entity_id": "STRING",
        "doc_type": "STRING",
        "total_net_amount": "STRING",
        "currency": "STRING",
        "delivery_status": "STRING",
        "requested_delivery_date": "STRING",
        "creation_date": "STRING",
        "pricing_date": "STRING",
        "payment_terms": "STRING",
        "incoterms": "STRING",
        "incoterms_location": "STRING",
        "billing_block": "STRING",
        "delivery_block": "STRING",
        "distribution_channel": "STRING",
        "division": "STRING",
        "delivery_count": "STRING",
        "is_fully_delivered": "STRING",
        "days_to_deliver": "STRING",
        "order_to_cash_days": "STRING",
        "fulfillment_rate": "STRING",
    },
    "Delivery": {
        "node_id": "STRING",
        "entity_id": "STRING",
        "shipping_point": "STRING",
        "goods_movement_status": "STRING",
        "picking_status": "STRING",
        "creation_date": "STRING",
        "actual_goods_movement_date": "STRING",
        "delivery_block": "STRING",
        "billing_block": "STRING",
        "incompletion_status": "STRING",
        "days_to_invoice": "STRING",
    },
    "BillingDocument": {
        "node_id": "STRING",
        "entity_id": "STRING",
        "doc_type": "STRING",
        "total_net_amount": "STRING",
        "currency": "STRING",
        "is_cancelled": "STRING",
        "billing_date": "STRING",
        "creation_date": "STRING",
        "fiscal_year": "STRING",
        "accounting_document": "STRING",
        "company_code": "STRING",
    },
    "JournalEntry": {
        "node_id": "STRING",
        "entity_id": "STRING",
        "gl_account": "STRING",
        "amount": "STRING",
        "currency": "STRING",
        "posting_date": "STRING",
        "document_date": "STRING",
        "document_type": "STRING",
        "profit_center": "STRING",
        "clearing_date": "STRING",
        "clearing_document": "STRING",
        "fiscal_year": "STRING",
        "account_type": "STRING",
        "cost_center": "STRING",
        "is_paid": "STRING",
        "is_self_cleared": "STRING",
        "days_to_pay": "STRING",
    },
}

# Each relationship: (rel_name, from_table, to_table, {prop_name: kuzu_type})
REL_SCHEMAS = {
    "PLACED_ORDER": {
        "from": "Customer",
        "to": "SalesOrder",
        "props": {},
    },
    "ORDER_CONTAINS": {
        "from": "SalesOrder",
        "to": "Product",
        "props": {
            "item_number": "STRING",
            "item_category": "STRING",
            "quantity": "STRING",
            "unit": "STRING",
            "net_amount": "STRING",
            "currency": "STRING",
            "material_group": "STRING",
            "production_plant": "STRING",
            "storage_location": "STRING",
            "confirmed_delivery_date": "STRING",
            "confirmed_quantity": "STRING",
            "qty_variance": "STRING",
            "has_shortfall": "STRING",
        },
    },
    "ORDER_FULFILLED_AT": {
        "from": "SalesOrder",
        "to": "Plant",
        "props": {},
    },
    "DELIVERED_BY": {
        "from": "SalesOrder",
        "to": "Delivery",
        "props": {},
    },
    "DELIVERY_CONTAINS": {
        "from": "Delivery",
        "to": "Product",
        "props": {
            "delivery_item": "STRING",
            "actual_quantity": "STRING",
            "unit": "STRING",
            "batch": "STRING",
            "plant": "STRING",
            "storage_location": "STRING",
        },
    },
    "INVOICED_BY": {
        "from": "Delivery",
        "to": "BillingDocument",
        "props": {
            "billing_item": "STRING",
            "material": "STRING",
            "billing_quantity": "STRING",
            "net_amount": "STRING",
            "currency": "STRING",
        },
    },
    "ORDER_INVOICED_BY": {
        "from": "SalesOrder",
        "to": "BillingDocument",
        "props": {
            "billing_item": "STRING",
            "material": "STRING",
            "billing_quantity": "STRING",
            "net_amount": "STRING",
            "currency": "STRING",
        },
    },
    "POSTED_AS": {
        "from": "BillingDocument",
        "to": "JournalEntry",
        "props": {},
    },
    "CLEARED_BY": {
        "from": "JournalEntry",
        "to": "JournalEntry",
        "props": {
            "clearing_date": "STRING",
        },
    },
    "AVAILABLE_AT": {
        "from": "Product",
        "to": "Plant",
        "props": {
            "profit_center": "STRING",
            "mrp_type": "STRING",
            "availability_check_type": "STRING",
            "country_of_origin": "STRING",
            "region_of_origin": "STRING",
        },
    },
    "CUSTOMER_BILLED": {
        "from": "Customer",
        "to": "BillingDocument",
        "props": {},
    },
    "CANCELS": {
        "from": "BillingDocument",
        "to": "BillingDocument",
        "props": {},
    },
}


# ─── Schema Creation ──────────────────────────────────────────────────────────

def create_schema(conn: kuzu.Connection):
    """Create all node and relationship tables in Kuzu."""
    # Node tables
    for table_name, props in NODE_SCHEMAS.items():
        cols = ", ".join(f"{name} {dtype}" for name, dtype in props.items())
        ddl = f"CREATE NODE TABLE IF NOT EXISTS {table_name}({cols}, PRIMARY KEY (node_id))"
        conn.execute(ddl)
        print(f"  ✓ Node table: {table_name}")

    # Relationship tables
    for rel_name, schema in REL_SCHEMAS.items():
        from_t, to_t = schema["from"], schema["to"]
        prop_cols = ", ".join(f"{name} {dtype}" for name, dtype in schema["props"].items())
        if prop_cols:
            ddl = f"CREATE REL TABLE IF NOT EXISTS {rel_name}(FROM {from_t} TO {to_t}, {prop_cols})"
        else:
            ddl = f"CREATE REL TABLE IF NOT EXISTS {rel_name}(FROM {from_t} TO {to_t})"
        conn.execute(ddl)
        print(f"  ✓ Rel table: {rel_name} ({from_t} → {to_t})")


# ─── Data Loading ─────────────────────────────────────────────────────────────

def _str_val(v) -> str:
    """Convert any value to a string for Kuzu insertion. None → empty string."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, list):
        return json.dumps(v)
    return str(v)


def _get_node_type(node_id: str) -> str:
    """Extract node type from a composite node_id like 'Customer:310000108'."""
    return node_id.split(":")[0]


def load_nodes(conn: kuzu.Connection, graph_data: dict):
    """Load all nodes from graph_data into Kuzu."""
    counts = {}
    for node_id, node_data in graph_data["nodes"].items():
        ntype = node_data["node_type"]
        schema = NODE_SCHEMAS.get(ntype)
        if not schema:
            continue

        # Build property values in schema order
        props = node_data["properties"]
        values = {}
        for prop_name in schema:
            if prop_name == "node_id":
                values[prop_name] = node_id
            else:
                orig_key = prop_name
                if prop_name == "entity_id": orig_key = "id"
                elif prop_name == "doc_type": orig_key = "type"
                elif prop_name == "product_group": orig_key = "group"
                values[prop_name] = _str_val(props.get(orig_key))

        # Build CREATE query with all properties
        prop_pairs = ", ".join(f"{k}: ${k}" for k in schema.keys())
        query = f"CREATE (:{ntype} {{{prop_pairs}}})"
        conn.execute(query, values)

        counts[ntype] = counts.get(ntype, 0) + 1

    for ntype, count in sorted(counts.items()):
        print(f"  ✓ Loaded {count} {ntype} nodes")


def load_edges(conn: kuzu.Connection, graph_data: dict):
    """Load all edges from graph_data into Kuzu."""
    counts = {}
    skipped = {}

    # Collect valid node IDs
    valid_nodes = set(graph_data["nodes"].keys())

    for edge in graph_data["edges"]:
        etype = edge["edge_type"]
        source = edge["source"]
        target = edge["target"]
        props = edge.get("properties", {})

        schema = REL_SCHEMAS.get(etype)
        if not schema:
            skipped[etype] = skipped.get(etype, 0) + 1
            continue

        # Skip edges where source/target doesn't exist in our nodes
        if source not in valid_nodes or target not in valid_nodes:
            skipped[etype] = skipped.get(etype, 0) + 1
            continue

        from_type = _get_node_type(source)
        to_type = _get_node_type(target)

        # Build property SET clause
        prop_values = {"src_id": source, "tgt_id": target}
        set_parts = []
        for prop_name in schema["props"]:
            orig_key = prop_name
            if prop_name == "entity_id": orig_key = "id"
            elif prop_name == "doc_type": orig_key = "type"
            elif prop_name == "product_group": orig_key = "group"

            val = _str_val(props.get(orig_key))
            prop_values[prop_name] = val
            set_parts.append(f"r.{prop_name} = ${prop_name}")

        query = (
            f"MATCH (a:{from_type} {{node_id: $src_id}}), "
            f"(b:{to_type} {{node_id: $tgt_id}}) "
            f"CREATE (a)-[r:{etype}]->(b)"
        )
        if set_parts:
            query += f" SET {', '.join(set_parts)}"

        try:
            conn.execute(query, prop_values)
            counts[etype] = counts.get(etype, 0) + 1
        except Exception as e:
            skipped[etype] = skipped.get(etype, 0) + 1

    for etype, count in sorted(counts.items()):
        print(f"  ✓ Loaded {count} {etype} edges")

    if skipped:
        for etype, count in sorted(skipped.items()):
            print(f"  ⚠ Skipped {count} {etype} edges (missing nodes or unknown type)")


# ─── Main API ─────────────────────────────────────────────────────────────────

def get_database(db_path: Path | None = None) -> kuzu.Database:
    """Open (or create) a Kuzu database."""
    path = db_path or KUZU_DB_DIR
    return kuzu.Database(str(path))


def get_connection(db: kuzu.Database) -> kuzu.Connection:
    """Get a connection to a Kuzu database."""
    return kuzu.Connection(db)


def load_from_graph_json(
    db_path: Path | None = None,
    graph_json_path: Path | None = None,
    force_rebuild: bool = False,
) -> kuzu.Database:
    """
    Full ETL: Read graph.json → Create Kuzu schema → Load all nodes & edges.

    Args:
        db_path: Directory for Kuzu database (default: graph_rag/output/kuzu_db/)
        graph_json_path: Path to graph.json (default: graph_rag/output/graph.json)
        force_rebuild: If True, delete existing DB and rebuild from scratch

    Returns:
        kuzu.Database instance
    """
    path = db_path or KUZU_DB_DIR
    json_path = graph_json_path or GRAPH_JSON_PATH

    if force_rebuild and path.exists():
        print(f"  Removing existing DB at {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    print(f"\n📂 Loading graph from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    meta = graph_data["metadata"]
    print(f"   Source: {meta['node_count']} nodes, {meta['edge_count']} edges")

    print(f"\n🗄️  Kuzu DB path: {path}")
    db = get_database(path)
    conn = get_connection(db)

    print("\n[1/3] Creating schema...")
    create_schema(conn)

    print("\n[2/3] Loading nodes...")
    load_nodes(conn, graph_data)

    print("\n[3/3] Loading edges...")
    load_edges(conn, graph_data)

    print("\n✅ Kuzu database ready!")
    return db


def verify_counts(db: kuzu.Database, graph_json_path: Path | None = None):
    """Verify that Kuzu counts match graph.json metadata."""
    json_path = graph_json_path or GRAPH_JSON_PATH
    with open(json_path, "r", encoding="utf-8") as f:
        meta = json.load(f)["metadata"]

    conn = get_connection(db)
    print("\n🔍 Verification:")

    all_ok = True

    # Node counts
    for ntype, expected in meta["node_types"].items():
        result = conn.execute(f"MATCH (n:{ntype}) RETURN count(n) AS cnt")
        while result.has_next():
            actual = result.get_next()[0]
        status = "✓" if actual == expected else "✗"
        if actual != expected:
            all_ok = False
        print(f"  {status} {ntype}: {actual}/{expected}")

    # Edge counts
    for etype, expected in meta["edge_types"].items():
        schema = REL_SCHEMAS.get(etype)
        if not schema:
            print(f"  ⊘ {etype}: skipped (not in schema)")
            continue
        from_t, to_t = schema["from"], schema["to"]
        result = conn.execute(
            f"MATCH (:{from_t})-[r:{etype}]->(:{to_t}) RETURN count(r) AS cnt"
        )
        while result.has_next():
            actual = result.get_next()[0]
        status = "✓" if actual == expected else "✗"
        if actual != expected:
            all_ok = False
        print(f"  {status} {etype}: {actual}/{expected}")

    if all_ok:
        print("\n  ✅ All counts match!")
    else:
        print("\n  ⚠️ Some counts don't match — check skipped edges above")

    return all_ok


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    verify = "--verify" in sys.argv
    force = "--force" in sys.argv or True  # Always force on direct run

    db = load_from_graph_json(force_rebuild=force)

    if verify or True:  # Always verify on direct run
        verify_counts(db)

    # Sample query
    conn = get_connection(db)
    print("\n📋 Sample Query — Top 3 customers by outstanding amount:")
    result = conn.execute("""
        MATCH (c:Customer)
        WHERE c.outstanding_amount <> ''
        RETURN c.name, c.outstanding_amount, c.total_orders
        ORDER BY c.outstanding_amount DESC
        LIMIT 3
    """)
    while result.has_next():
        row = result.get_next()
        print(f"   {row[0]} | Outstanding: ₹{row[1]} | Orders: {row[2]}")

    print("\n🔗 Sample Query — O2C chain for a sales order:")
    result = conn.execute("""
        MATCH (c:Customer)-[:PLACED_ORDER]->(so:SalesOrder)-[:DELIVERED_BY]->(d:Delivery)-[:INVOICED_BY]->(bd:BillingDocument)-[:POSTED_AS]->(je:JournalEntry)
        RETURN c.name, so.node_id, d.node_id, bd.node_id, je.node_id, je.is_paid
        LIMIT 3
    """)
    while result.has_next():
        row = result.get_next()
        print(f"   {row[0]} → {row[1]} → {row[2]} → {row[3]} → {row[4]} (paid: {row[5]})")
