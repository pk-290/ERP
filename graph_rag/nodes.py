"""
Node extraction module.
Transforms raw JSONL records into clean graph nodes with typed properties.

Design principles:
  1. Every node gets a globally unique `node_id` = "{NodeType}:{id}"
  2. Properties are cleaned (empty strings → None, numeric strings → float)
  3. Original record stored in `_raw` for zero data loss
  4. Foreign keys prefixed with `_` are extracted but NOT stored as node properties
     (they're used by edge extraction instead)
"""
import json
from datetime import datetime
from typing import Any

from .config import (
    CUSTOMER, PRODUCT, PLANT, SALES_ORDER, DELIVERY, BILLING_DOC, JOURNAL_ENTRY,
    CUSTOMER_FIELDS, CUSTOMER_ADDRESS_FIELDS, CUSTOMER_COMPANY_FIELDS,
    CUSTOMER_SALES_AREA_FIELDS, PRODUCT_FIELDS, PLANT_FIELDS,
    SALES_ORDER_FIELDS, DELIVERY_FIELDS, BILLING_DOC_FIELDS, JOURNAL_ENTRY_FIELDS,
)
from .loader import load_entity


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _clean_value(val: Any) -> Any:
    """Normalize a raw field value."""
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if val == "":
            return None
        # Try numeric conversion for amount/qty fields
        try:
            return float(val) if "." in val else int(val)
        except ValueError:
            return val
    if isinstance(val, dict):
        # Time objects like {"hours": 11, "minutes": 31, "seconds": 13}
        if "hours" in val:
            return f"{val['hours']:02d}:{val['minutes']:02d}:{val['seconds']:02d}"
        return val
    return val


def _extract_props(record: dict, field_map: dict[str, str]) -> dict[str, Any]:
    """Extract and clean properties from a record using a field mapping."""
    props = {}
    for raw_field, clean_name in field_map.items():
        if raw_field in record:
            cleaned = _clean_value(record[raw_field])
            # Skip FK fields (prefixed with _) from node properties
            if not clean_name.startswith("_"):
                props[clean_name] = cleaned
            else:
                # Store FKs in a separate namespace so edges can use them
                props[clean_name] = cleaned
    return props


def _make_node(node_type: str, node_id: str, props: dict, raw: dict) -> dict:
    """Create a standardized node dict."""
    return {
        "node_id": f"{node_type}:{node_id}",
        "node_type": node_type,
        "properties": {k: v for k, v in props.items() if not k.startswith("_")},
        "_fks": {k: v for k, v in props.items() if k.startswith("_")},
        "_raw": raw,
    }


# ─── Node Extractors ────────────────────────────────────────────────────────

def extract_customers() -> list[dict]:
    """
    Build Customer nodes by merging 4 source entities:
      - business_partners (core identity)
      - business_partner_addresses (location — 1:1 merge)
      - customer_company_assignments (financial config)
      - customer_sales_area_assignments (commercial config — 1:N, store primary + list)
    """
    bp_records = load_entity("business_partners")
    addr_records = load_entity("business_partner_addresses")
    company_records = load_entity("customer_company_assignments")
    sales_area_records = load_entity("customer_sales_area_assignments")

    # Index lookups
    addr_by_bp = {r["businessPartner"]: r for r in addr_records}
    company_by_cust = {r["customer"]: r for r in company_records}

    # Sales areas: group by customer (one customer can have multiple)
    sales_areas_by_cust: dict[str, list[dict]] = {}
    for r in sales_area_records:
        sales_areas_by_cust.setdefault(r["customer"], []).append(r)

    nodes = []
    for bp in bp_records:
        bp_id = bp["businessPartner"]

        # Core properties from business_partners
        props = _extract_props(bp, CUSTOMER_FIELDS)

        # Merge address
        if bp_id in addr_by_bp:
            addr_props = _extract_props(addr_by_bp[bp_id], CUSTOMER_ADDRESS_FIELDS)
            props.update(addr_props)

        # Merge company assignment
        if bp_id in company_by_cust:
            comp_props = _extract_props(company_by_cust[bp_id], CUSTOMER_COMPANY_FIELDS)
            props.update(comp_props)

        # Merge sales area (primary = first assignment)
        areas = sales_areas_by_cust.get(bp_id, [])
        if areas:
            primary_area = _extract_props(areas[0], CUSTOMER_SALES_AREA_FIELDS)
            props.update(primary_area)
            # Store ALL sales areas as a list for completeness
            props["_all_sales_areas"] = [
                _extract_props(a, CUSTOMER_SALES_AREA_FIELDS) for a in areas
            ]

        # Build raw composite for zero data loss
        raw_composite = {
            "business_partner": bp,
            "address": addr_by_bp.get(bp_id),
            "company_assignment": company_by_cust.get(bp_id),
            "sales_area_assignments": areas,
        }

        node = _make_node(CUSTOMER, bp_id, props, raw_composite)
        # Promote sales areas list into properties for agent access
        node["properties"]["sales_area_count"] = len(areas)
        nodes.append(node)

    return nodes


def extract_products() -> list[dict]:
    """
    Build Product nodes by merging:
      - products (core)
      - product_descriptions (human-readable name)
    """
    prod_records = load_entity("products")
    desc_records = load_entity("product_descriptions")

    # Index: product → description (EN preferred)
    desc_by_prod: dict[str, str] = {}
    for r in desc_records:
        # Prefer EN, but take whatever is available
        if r.get("language") == "EN" or r["product"] not in desc_by_prod:
            desc_by_prod[r["product"]] = r.get("productDescription", "")

    nodes = []
    for prod in prod_records:
        prod_id = prod["product"]
        props = _extract_props(prod, PRODUCT_FIELDS)
        props["description"] = desc_by_prod.get(prod_id)

        raw = {"product": prod, "description_record": {"product": prod_id, "description": desc_by_prod.get(prod_id)}}
        nodes.append(_make_node(PRODUCT, prod_id, props, raw))

    return nodes


def extract_plants() -> list[dict]:
    """Build Plant nodes from plants entity."""
    records = load_entity("plants")
    nodes = []
    for r in records:
        props = _extract_props(r, PLANT_FIELDS)
        nodes.append(_make_node(PLANT, r["plant"], props, r))
    return nodes


def extract_sales_orders() -> list[dict]:
    """Build SalesOrder nodes from sales_order_headers."""
    records = load_entity("sales_order_headers")
    nodes = []
    for r in records:
        props = _extract_props(r, SALES_ORDER_FIELDS)
        nodes.append(_make_node(SALES_ORDER, r["salesOrder"], props, r))
    return nodes


def extract_deliveries() -> list[dict]:
    """Build Delivery nodes from outbound_delivery_headers."""
    records = load_entity("outbound_delivery_headers")
    nodes = []
    for r in records:
        props = _extract_props(r, DELIVERY_FIELDS)
        nodes.append(_make_node(DELIVERY, r["deliveryDocument"], props, r))
    return nodes


def extract_billing_documents() -> list[dict]:
    """Build BillingDocument nodes from billing_document_headers."""
    records = load_entity("billing_document_headers")
    nodes = []
    for r in records:
        props = _extract_props(r, BILLING_DOC_FIELDS)
        nodes.append(_make_node(BILLING_DOC, r["billingDocument"], props, r))
    return nodes


def extract_journal_entries() -> list[dict]:
    """Build JournalEntry nodes from journal_entry_items_accounts_receivable."""
    records = load_entity("journal_entry_items_accounts_receivable")
    nodes = []
    for r in records:
        props = _extract_props(r, JOURNAL_ENTRY_FIELDS)
        nodes.append(_make_node(JOURNAL_ENTRY, r["accountingDocument"], props, r))
    return nodes


# ─── Master extractor ────────────────────────────────────────────────────────

def extract_all_nodes() -> dict[str, list[dict]]:
    """Run all node extractors and return {node_type: [nodes]}."""
    return {
        CUSTOMER: extract_customers(),
        PRODUCT: extract_products(),
        PLANT: extract_plants(),
        SALES_ORDER: extract_sales_orders(),
        DELIVERY: extract_deliveries(),
        BILLING_DOC: extract_billing_documents(),
        JOURNAL_ENTRY: extract_journal_entries(),
    }
