"""
Edge extraction module.
Transforms raw JSONL join-records into explicit graph edges.

Design principles:
  1. Every edge has: source_id, target_id, edge_type, properties
  2. IDs use global format: "{NodeType}:{id}"
  3. Item-level records (sales_order_items, delivery_items, billing_items)
     become edges with properties — NOT separate nodes
  4. Schedule lines are merged INTO the ORDER_CONTAINS edge
  5. Storage locations are merged INTO the AVAILABLE_AT edge
"""
from typing import Any

from .config import (
    CUSTOMER, PRODUCT, PLANT, SALES_ORDER, DELIVERY, BILLING_DOC, JOURNAL_ENTRY,
    PLACED_ORDER, ORDER_CONTAINS, ORDER_FULFILLED_AT, DELIVERED_BY,
    DELIVERY_CONTAINS, INVOICED_BY, POSTED_AS, CLEARED_BY, AVAILABLE_AT, CANCELS,
    CUSTOMER_BILLED,
)
from .loader import load_entity
from .nodes import _clean_value


def _make_edge(edge_type: str, source_id: str, target_id: str,
               props: dict | None = None, raw: dict | None = None) -> dict:
    """Create a standardized edge dict."""
    return {
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": edge_type,
        "properties": props or {},
        "_raw": raw,
    }


# ─── Edge Extractors ────────────────────────────────────────────────────────

def extract_placed_order_edges(order_nodes: list[dict]) -> list[dict]:
    """
    Customer --PLACED_ORDER--> SalesOrder
    Source: sales_order_headers.soldToParty → customer id
    """
    edges = []
    for node in order_nodes:
        customer_id = node["_fks"].get("_customer_id")
        if customer_id:
            edges.append(_make_edge(
                PLACED_ORDER,
                f"{CUSTOMER}:{customer_id}",
                node["node_id"],
            ))
    return edges


def extract_order_contains_edges() -> list[dict]:
    """
    SalesOrder --ORDER_CONTAINS--> Product
    Source: sales_order_items (qty, amount, material_group)
    Enriched with: sales_order_schedule_lines (confirmed date, confirmed qty)

    Why merge schedule lines here?
      Schedule lines describe WHEN and HOW MUCH of an item will be delivered.
      They always attach to an order+item pair — same key as ORDER_CONTAINS.
      Keeping them as edge props means:
        "When was item 10 of order 740506 confirmed?" → read edge property directly.
    """
    items = load_entity("sales_order_items")
    schedule_lines = load_entity("sales_order_schedule_lines")

    # Index schedule lines by (salesOrder, salesOrderItem)
    sched_by_key: dict[tuple, list[dict]] = {}
    for sl in schedule_lines:
        key = (sl["salesOrder"], sl["salesOrderItem"])
        sched_by_key.setdefault(key, []).append(sl)

    edges = []
    for item in items:
        so_id = item["salesOrder"]
        product_id = item.get("material")
        if not product_id:
            continue

        item_key = (so_id, item["salesOrderItem"])

        # Base properties from the item
        props = {
            "item_number": _clean_value(item.get("salesOrderItem")),
            "item_category": _clean_value(item.get("salesOrderItemCategory")),
            "quantity": _clean_value(item.get("requestedQuantity")),
            "unit": _clean_value(item.get("requestedQuantityUnit")),
            "net_amount": _clean_value(item.get("netAmount")),
            "currency": _clean_value(item.get("transactionCurrency")),
            "material_group": _clean_value(item.get("materialGroup")),
            "production_plant": _clean_value(item.get("productionPlant")),
            "storage_location": _clean_value(item.get("storageLocation")),
        }

        # Merge schedule line data
        scheds = sched_by_key.get(item_key, [])
        if scheds:
            # Take the first (most common case: single schedule line per item)
            sl = scheds[0]
            props["confirmed_delivery_date"] = _clean_value(sl.get("confirmedDeliveryDate"))
            props["confirmed_quantity"] = _clean_value(sl.get("confdOrderQtyByMatlAvailCheck"))
            if len(scheds) > 1:
                props["_all_schedule_lines"] = [
                    {
                        "line": _clean_value(s.get("scheduleLine")),
                        "confirmed_date": _clean_value(s.get("confirmedDeliveryDate")),
                        "confirmed_qty": _clean_value(s.get("confdOrderQtyByMatlAvailCheck")),
                    }
                    for s in scheds
                ]

        raw = {"sales_order_item": item, "schedule_lines": scheds}
        edges.append(_make_edge(
            ORDER_CONTAINS,
            f"{SALES_ORDER}:{so_id}",
            f"{PRODUCT}:{product_id}",
            props, raw,
        ))

    return edges


def extract_order_fulfilled_at_edges() -> list[dict]:
    """
    SalesOrder --ORDER_FULFILLED_AT--> Plant
    Source: sales_order_items.productionPlant
    Deduplicated: one edge per unique (order, plant) pair.
    """
    items = load_entity("sales_order_items")
    seen = set()
    edges = []

    for item in items:
        so_id = item["salesOrder"]
        plant_id = _clean_value(item.get("productionPlant"))
        if not plant_id:
            continue

        key = (so_id, plant_id)
        if key in seen:
            continue
        seen.add(key)

        edges.append(_make_edge(
            ORDER_FULFILLED_AT,
            f"{SALES_ORDER}:{so_id}",
            f"{PLANT}:{plant_id}",
        ))

    return edges


def extract_delivered_by_edges() -> list[dict]:
    """
    SalesOrder --DELIVERED_BY--> Delivery
    Source: outbound_delivery_items.referenceSdDocument → salesOrder
    Deduplicated: one edge per unique (order, delivery) pair.
    """
    del_items = load_entity("outbound_delivery_items")
    seen = set()
    edges = []

    for item in del_items:
        del_id = item["deliveryDocument"]
        so_ref = _clean_value(item.get("referenceSdDocument"))
        if not so_ref:
            continue

        key = (so_ref, del_id)
        if key in seen:
            continue
        seen.add(key)

        edges.append(_make_edge(
            DELIVERED_BY,
            f"{SALES_ORDER}:{so_ref}",
            f"{DELIVERY}:{del_id}",
        ))

    return edges


def extract_delivery_contains_edges() -> list[dict]:
    """
    Delivery --DELIVERY_CONTAINS--> Product
    Source: outbound_delivery_items (actual qty, batch, plant, storage)

    NOTE: delivery items don't have a direct `material` field in our data.
    They reference the sales order item which has the material.
    So we join: delivery_item → sales_order_item (via referenceSdDocument + item) → material

    If that join fails, we skip (delivery item without product link).
    """
    del_items = load_entity("outbound_delivery_items")
    so_items = load_entity("sales_order_items")

    # Index: (salesOrder, item_padded) → material
    # delivery uses "000010" format, sales order uses "10" — need to handle both
    material_by_so_item: dict[tuple, str] = {}
    for si in so_items:
        # Store with both padded and unpadded keys
        so = si["salesOrder"]
        item = si["salesOrderItem"]
        material_by_so_item[(so, item)] = si["material"]
        # Also store zero-padded version
        padded = item.zfill(6)
        material_by_so_item[(so, padded)] = si["material"]

    edges = []
    for di in del_items:
        del_id = di["deliveryDocument"]
        so_ref = _clean_value(di.get("referenceSdDocument"))
        so_item_ref = _clean_value(di.get("referenceSdDocumentItem"))

        if not so_ref or not so_item_ref:
            continue

        # Look up material from the referenced sales order item
        material = (
            material_by_so_item.get((str(so_ref), str(so_item_ref)))
            or material_by_so_item.get((str(so_ref), str(so_item_ref).zfill(6)))
            or material_by_so_item.get((str(so_ref), str(so_item_ref).lstrip("0") or "0"))
        )

        if not material:
            continue

        props = {
            "delivery_item": _clean_value(di.get("deliveryDocumentItem")),
            "actual_quantity": _clean_value(di.get("actualDeliveryQuantity")),
            "unit": _clean_value(di.get("deliveryQuantityUnit")),
            "batch": _clean_value(di.get("batch")),
            "plant": _clean_value(di.get("plant")),
            "storage_location": _clean_value(di.get("storageLocation")),
        }

        edges.append(_make_edge(
            DELIVERY_CONTAINS,
            f"{DELIVERY}:{del_id}",
            f"{PRODUCT}:{material}",
            props, di,
        ))

    return edges


def extract_invoiced_by_edges() -> list[dict]:
    """
    Delivery --INVOICED_BY--> BillingDocument
    Source: billing_document_items.referenceSdDocument → deliveryDocument

    NOTE: referenceSdDocument in billing items can point to either a delivery
    or a sales order. We check if the reference matches a known delivery ID.
    If not, we create a SalesOrder→BillingDocument edge instead (as ORDER_INVOICED_BY).
    """
    billing_items = load_entity("billing_document_items")
    del_headers = load_entity("outbound_delivery_headers")

    delivery_ids = {r["deliveryDocument"] for r in del_headers}

    edges = []
    seen = set()

    for bi in billing_items:
        bill_id = bi["billingDocument"]
        ref = _clean_value(bi.get("referenceSdDocument"))
        if not ref:
            continue

        ref_str = str(ref)

        if ref_str in delivery_ids:
            key = (ref_str, bill_id, INVOICED_BY)
            if key not in seen:
                seen.add(key)
                props = {
                    "billing_item": _clean_value(bi.get("billingDocumentItem")),
                    "material": _clean_value(bi.get("material")),
                    "billing_quantity": _clean_value(bi.get("billingQuantity")),
                    "net_amount": _clean_value(bi.get("netAmount")),
                    "currency": _clean_value(bi.get("transactionCurrency")),
                }
                edges.append(_make_edge(
                    INVOICED_BY,
                    f"{DELIVERY}:{ref_str}",
                    f"{BILLING_DOC}:{bill_id}",
                    props, bi,
                ))
        else:
            # Reference is to a sales order directly (no delivery intermediate)
            key = (ref_str, bill_id, "ORDER_INVOICED_BY")
            if key not in seen:
                seen.add(key)
                props = {
                    "billing_item": _clean_value(bi.get("billingDocumentItem")),
                    "material": _clean_value(bi.get("material")),
                    "billing_quantity": _clean_value(bi.get("billingQuantity")),
                    "net_amount": _clean_value(bi.get("netAmount")),
                    "currency": _clean_value(bi.get("transactionCurrency")),
                }
                edges.append(_make_edge(
                    "ORDER_INVOICED_BY",
                    f"{SALES_ORDER}:{ref_str}",
                    f"{BILLING_DOC}:{bill_id}",
                    props, bi,
                ))

    return edges


def extract_posted_as_edges(billing_nodes: list[dict], je_nodes: list[dict]) -> list[dict]:
    """
    BillingDocument --POSTED_AS--> JournalEntry
    Source: billing_document_headers.accountingDocument = journal_entry.accountingDocument

    Also matches via journal_entry.referenceDocument → billingDocument
    """
    # Build lookup: accountingDocument → JournalEntry node_id
    je_by_acct_doc = {}
    je_by_ref_doc = {}
    for je in je_nodes:
        je_by_acct_doc[je["properties"].get("id")] = je["node_id"]
        ref = je["_fks"].get("_reference_document")
        if ref:
            je_by_ref_doc[str(ref)] = je["node_id"]

    edges = []
    seen = set()

    for bd in billing_nodes:
        bill_id = bd["properties"]["id"]
        acct_doc = bd["properties"].get("accounting_document")

        # Match by accounting_document field on billing header
        if acct_doc and str(acct_doc) in je_by_acct_doc:
            target = je_by_acct_doc[str(acct_doc)]
            key = (bd["node_id"], target)
            if key not in seen:
                seen.add(key)
                edges.append(_make_edge(POSTED_AS, bd["node_id"], target))

        # Match by journal entry referencing this billing doc
        if str(bill_id) in je_by_ref_doc:
            target = je_by_ref_doc[str(bill_id)]
            key = (bd["node_id"], target)
            if key not in seen:
                seen.add(key)
                edges.append(_make_edge(POSTED_AS, bd["node_id"], target))

    return edges


def extract_cleared_by_edges(je_nodes: list[dict]) -> list[dict]:
    """
    JournalEntry --CLEARED_BY--> JournalEntry (payment)
    Source: journal_entry.clearingAccountingDocument

    A journal entry that has a clearingAccountingDocument means it was settled
    by another accounting document (the payment). If clearing doc == self,
    it was a self-clearing entry (e.g., credit memo).
    """
    je_ids = {n["properties"]["id"] for n in je_nodes}

    edges = []
    for je in je_nodes:
        je_id = je["properties"]["id"]
        clearing_doc = je["properties"].get("clearing_document")
        clearing_date = je["properties"].get("clearing_date")

        if clearing_doc and clearing_doc != je_id:
            # Only create edge if clearing doc is different from self
            props = {"clearing_date": clearing_date}
            edges.append(_make_edge(
                CLEARED_BY,
                je["node_id"],
                f"{JOURNAL_ENTRY}:{clearing_doc}",
                props,
            ))

    return edges


def extract_available_at_edges() -> list[dict]:
    """
    Product --AVAILABLE_AT--> Plant
    Source: product_plants + product_storage_locations (merged)

    Storage locations are gathered into a list on the edge, e.g.:
      Product:X --AVAILABLE_AT{storage_locations: ["5044","5066"], mrp_type: "ND"}--> Plant:MH05

    Why merge storage locations here?
      product_storage_locations has 16k records but only adds one field per (product, plant, loc).
      Making each a separate node would bloat the graph with 16k nodes that connect nothing new.
      Instead, they become a list property on the Product→Plant edge.
    """
    pp_records = load_entity("product_plants")
    psl_records = load_entity("product_storage_locations")

    # Group storage locations by (product, plant)
    storage_by_key: dict[tuple, list[str]] = {}
    for psl in psl_records:
        key = (psl["product"], psl["plant"])
        loc = _clean_value(psl.get("storageLocation"))
        if loc:
            storage_by_key.setdefault(key, []).append(str(loc))

    edges = []
    for pp in pp_records:
        product_id = pp["product"]
        plant_id = pp["plant"]
        key = (product_id, plant_id)

        props = {
            "profit_center": _clean_value(pp.get("profitCenter")),
            "mrp_type": _clean_value(pp.get("mrpType")),
            "availability_check_type": _clean_value(pp.get("availabilityCheckType")),
            "country_of_origin": _clean_value(pp.get("countryOfOrigin")),
            "region_of_origin": _clean_value(pp.get("regionOfOrigin")),
            "storage_locations": storage_by_key.get(key, []),
        }

        edges.append(_make_edge(
            AVAILABLE_AT,
            f"{PRODUCT}:{product_id}",
            f"{PLANT}:{plant_id}",
            props, pp,
        ))

    return edges


def extract_cancellation_edges() -> list[dict]:
    """
    BillingDocument --CANCELS--> BillingDocument
    Source: billing_document_cancellations

    The cancellation record's billingDocument is the cancellation doc.
    cancelledBillingDocument is the original that was cancelled.
    If cancelledBillingDocument is empty, the record IS the cancelled doc
    (marked via billingDocumentIsCancelled=true).
    """
    cancellations = load_entity("billing_document_cancellations")
    edges = []

    for c in cancellations:
        cancel_doc = c["billingDocument"]
        original_doc = _clean_value(c.get("cancelledBillingDocument"))

        if original_doc:
            # cancel_doc cancels original_doc
            edges.append(_make_edge(
                CANCELS,
                f"{BILLING_DOC}:{cancel_doc}",
                f"{BILLING_DOC}:{original_doc}",
                raw=c,
            ))
        # If no cancelledBillingDocument, this doc was cancelled but we don't
        # know by which doc — mark it on the node instead (handled in precompute)

    return edges


def extract_customer_billed_edges(billing_nodes: list[dict]) -> list[dict]:
    """
    Customer --CUSTOMER_BILLED--> BillingDocument
    Source: billing_document_headers.soldToParty

    WHY: Billing docs have a direct customer reference. Without this edge,
    customer aggregates can only find invoices through the
    order→delivery→invoice chain. If any link is missing (e.g., order not
    in sample), the customer's billing total would be wrong.
    This edge is the REDUNDANT but CRITICAL shortcut for accurate aggregates.
    """
    edges = []
    for bn in billing_nodes:
        customer_id = bn["_fks"].get("_customer_id")
        if customer_id:
            edges.append(_make_edge(
                CUSTOMER_BILLED,
                f"{CUSTOMER}:{customer_id}",
                bn["node_id"],
            ))
    return edges


# ─── Master extractor ────────────────────────────────────────────────────────

def extract_all_edges(nodes_by_type: dict[str, list[dict]]) -> list[dict]:
    """Run all edge extractors and return flat list of edges."""
    all_edges = []

    all_edges.extend(extract_placed_order_edges(nodes_by_type[SALES_ORDER]))
    all_edges.extend(extract_order_contains_edges())
    all_edges.extend(extract_order_fulfilled_at_edges())
    all_edges.extend(extract_delivered_by_edges())
    all_edges.extend(extract_delivery_contains_edges())
    all_edges.extend(extract_invoiced_by_edges())
    all_edges.extend(extract_posted_as_edges(
        nodes_by_type[BILLING_DOC], nodes_by_type[JOURNAL_ENTRY]
    ))
    all_edges.extend(extract_cleared_by_edges(nodes_by_type[JOURNAL_ENTRY]))
    all_edges.extend(extract_available_at_edges())
    all_edges.extend(extract_cancellation_edges())
    all_edges.extend(extract_customer_billed_edges(nodes_by_type[BILLING_DOC]))

    return all_edges
