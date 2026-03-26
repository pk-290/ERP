"""
Precompute engine.
Adds derived properties to nodes and edges AFTER the graph is assembled.

These are properties that don't exist in raw data but are critical for
the agent to answer business questions without doing multi-hop math at query time.

Categories:
  1. Status flags   — is_paid, is_fully_delivered, is_cancelled
  2. Cycle times    — days_to_deliver, days_to_invoice, days_to_pay, order_to_cash_days
  3. Aggregations   — total_billed_amount, total_orders, outstanding_amount
  4. Variance       — qty_variance, amount_variance
  5. Popularity     — product_order_count, plant_order_count
"""
from datetime import datetime
from typing import Any

from .config import (
    CUSTOMER, PRODUCT, PLANT, SALES_ORDER, DELIVERY, BILLING_DOC, JOURNAL_ENTRY,
    PLACED_ORDER, ORDER_CONTAINS, ORDER_FULFILLED_AT, DELIVERED_BY,
    DELIVERY_CONTAINS, INVOICED_BY, POSTED_AS, CLEARED_BY, AVAILABLE_AT, CANCELS,
)


def _parse_date(val: Any) -> datetime | None:
    """Parse a date value (string or datetime) into a datetime object."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        # Handle ISO format like "2025-04-02T00:00:00.000Z"
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return None


def _days_between(d1: Any, d2: Any) -> int | None:
    """Calculate days between two dates. Returns None if either is missing."""
    dt1 = _parse_date(d1)
    dt2 = _parse_date(d2)
    if dt1 and dt2:
        return abs((dt2 - dt1).days)
    return None


# ─── Graph index helpers ─────────────────────────────────────────────────────

class GraphIndex:
    """
    Lightweight index over nodes and edges for fast lookup during precompute.
    Avoids O(n²) loops by building hash-based indexes once.
    """

    def __init__(self, nodes_by_type: dict[str, list[dict]], edges: list[dict]):
        self.nodes_by_type = nodes_by_type
        self.edges = edges

        # Node lookup: node_id → node
        self.node_by_id: dict[str, dict] = {}
        for ntype, nlist in nodes_by_type.items():
            for n in nlist:
                self.node_by_id[n["node_id"]] = n

        # Edge indexes
        self.edges_by_type: dict[str, list[dict]] = {}
        self.edges_from: dict[str, list[dict]] = {}   # source_id → edges
        self.edges_to: dict[str, list[dict]] = {}     # target_id → edges

        for e in edges:
            self.edges_by_type.setdefault(e["edge_type"], []).append(e)
            self.edges_from.setdefault(e["source_id"], []).append(e)
            self.edges_to.setdefault(e["target_id"], []).append(e)

    def get_edges(self, edge_type: str) -> list[dict]:
        return self.edges_by_type.get(edge_type, [])

    def get_outgoing(self, node_id: str, edge_type: str | None = None) -> list[dict]:
        edges = self.edges_from.get(node_id, [])
        if edge_type:
            return [e for e in edges if e["edge_type"] == edge_type]
        return edges

    def get_incoming(self, node_id: str, edge_type: str | None = None) -> list[dict]:
        edges = self.edges_to.get(node_id, [])
        if edge_type:
            return [e for e in edges if e["edge_type"] == edge_type]
        return edges

    def get_node(self, node_id: str) -> dict | None:
        return self.node_by_id.get(node_id)


# ─── Precompute functions ────────────────────────────────────────────────────

def precompute_journal_entry_flags(idx: GraphIndex):
    """
    JournalEntry.is_paid = True if clearing_date is not None
    JournalEntry.is_self_cleared = True if clearing_document == self.id

    WHY: Most common question is "what's unpaid?" — this makes it a simple filter.
    """
    for je in idx.nodes_by_type.get(JOURNAL_ENTRY, []):
        props = je["properties"]
        clearing_date = props.get("clearing_date")
        clearing_doc = props.get("clearing_document")
        je_id = props.get("id")

        props["is_paid"] = clearing_date is not None
        props["is_self_cleared"] = (clearing_doc is not None and str(clearing_doc) == str(je_id))


def precompute_sales_order_cycle_times(idx: GraphIndex):
    """
    SalesOrder.days_to_deliver = earliest delivery creation_date - order creation_date
    SalesOrder.is_fully_delivered = delivery_status == 'C'
    SalesOrder.delivery_count = number of deliveries

    WHY: "How fast are we delivering?" requires knowing the gap without traversing.
    """
    for so in idx.nodes_by_type.get(SALES_ORDER, []):
        props = so["properties"]
        order_date = props.get("creation_date")

        # Find associated deliveries
        delivered_edges = idx.get_outgoing(so["node_id"], DELIVERED_BY)
        props["delivery_count"] = len(delivered_edges)
        props["is_fully_delivered"] = props.get("delivery_status") == "C"

        # Earliest delivery date
        min_del_days = None
        for de in delivered_edges:
            del_node = idx.get_node(de["target_id"])
            if del_node:
                del_date = del_node["properties"].get("creation_date")
                days = _days_between(order_date, del_date)
                if days is not None:
                    if min_del_days is None or days < min_del_days:
                        min_del_days = days

        props["days_to_deliver"] = min_del_days


def precompute_delivery_cycle_times(idx: GraphIndex):
    """
    Delivery.days_to_invoice = earliest billing creation_date - delivery creation_date

    WHY: Billing cycle time analysis.
    """
    for dl in idx.nodes_by_type.get(DELIVERY, []):
        props = dl["properties"]
        del_date = props.get("creation_date")

        invoice_edges = idx.get_outgoing(dl["node_id"], INVOICED_BY)
        min_invoice_days = None

        for ie in invoice_edges:
            bill_node = idx.get_node(ie["target_id"])
            if bill_node:
                bill_date = bill_node["properties"].get("creation_date")
                days = _days_between(del_date, bill_date)
                if days is not None:
                    if min_invoice_days is None or days < min_invoice_days:
                        min_invoice_days = days

        props["days_to_invoice"] = min_invoice_days


def precompute_journal_entry_cycle_times(idx: GraphIndex):
    """
    JournalEntry.days_to_pay = clearing_date - posting_date

    WHY: "Average time to collect payment" — key AR metric.
    """
    for je in idx.nodes_by_type.get(JOURNAL_ENTRY, []):
        props = je["properties"]
        props["days_to_pay"] = _days_between(
            props.get("posting_date"),
            props.get("clearing_date"),
        )


def precompute_order_to_cash(idx: GraphIndex):
    """
    SalesOrder.order_to_cash_days = payment clearing_date - order creation_date

    Full cycle: Order → Delivery → Invoice → Journal Entry → Payment
    We traverse the chain and find the latest clearing_date.

    WHY: The ultimate O2C metric. "How long from order to cash in bank?"
    """
    for so in idx.nodes_by_type.get(SALES_ORDER, []):
        props = so["properties"]
        order_date = props.get("creation_date")

        # Walk: Order → Delivery → BillingDoc → JournalEntry (check clearing_date)
        latest_clearing = None

        # Path 1: via deliveries
        for del_edge in idx.get_outgoing(so["node_id"], DELIVERED_BY):
            for inv_edge in idx.get_outgoing(del_edge["target_id"], INVOICED_BY):
                for post_edge in idx.get_outgoing(inv_edge["target_id"], POSTED_AS):
                    je_node = idx.get_node(post_edge["target_id"])
                    if je_node:
                        cd = _parse_date(je_node["properties"].get("clearing_date"))
                        if cd and (latest_clearing is None or cd > latest_clearing):
                            latest_clearing = cd

        # Path 2: via direct ORDER_INVOICED_BY
        for inv_edge in idx.get_outgoing(so["node_id"], "ORDER_INVOICED_BY"):
            for post_edge in idx.get_outgoing(inv_edge["target_id"], POSTED_AS):
                je_node = idx.get_node(post_edge["target_id"])
                if je_node:
                    cd = _parse_date(je_node["properties"].get("clearing_date"))
                    if cd and (latest_clearing is None or cd > latest_clearing):
                        latest_clearing = cd

        if latest_clearing and order_date:
            props["order_to_cash_days"] = _days_between(order_date, latest_clearing)
        else:
            props["order_to_cash_days"] = None


def precompute_customer_aggregates(idx: GraphIndex):
    """
    Customer.total_orders          = count of PLACED_ORDER edges
    Customer.total_billed_amount   = sum of non-cancelled billing doc amounts
    Customer.outstanding_amount    = sum of unpaid journal entry amounts
    Customer.avg_days_to_pay       = average days_to_pay across paid journal entries

    WHY: Customer-level KPIs without running aggregation at query time.
    """
    for cust in idx.nodes_by_type.get(CUSTOMER, []):
        props = cust["properties"]

        # Count orders
        order_edges = idx.get_outgoing(cust["node_id"], PLACED_ORDER)
        props["total_orders"] = len(order_edges)

        # Use the direct CUSTOMER_BILLED edge (most reliable — doesn't depend
        # on order→delivery→invoice chain being complete in the sample)
        total_billed = 0.0
        billing_doc_ids = set()

        for be in idx.get_outgoing(cust["node_id"], "CUSTOMER_BILLED"):
            bd = idx.get_node(be["target_id"])
            if bd and bd["properties"]["id"] not in billing_doc_ids:
                billing_doc_ids.add(bd["properties"]["id"])
                if not bd["properties"].get("is_cancelled"):
                    amt = bd["properties"].get("total_net_amount")
                    if amt is not None:
                        total_billed += float(amt)

        props["total_billed_amount"] = round(total_billed, 2)
        props["billing_doc_count"] = len(billing_doc_ids)

        # Outstanding = sum of unpaid journal entries for this customer
        outstanding = 0.0
        paid_days = []

        for je in idx.nodes_by_type.get(JOURNAL_ENTRY, []):
            je_cust = je["_fks"].get("_customer_id")
            if str(je_cust) != str(props.get("id")):
                continue

            amt = je["properties"].get("amount")
            if amt is not None:
                amt_f = float(amt)
                if not je["properties"].get("is_paid"):
                    outstanding += abs(amt_f)
                else:
                    dtp = je["properties"].get("days_to_pay")
                    if dtp is not None:
                        paid_days.append(dtp)

        props["outstanding_amount"] = round(outstanding, 2)
        props["avg_days_to_pay"] = (
            round(sum(paid_days) / len(paid_days), 1) if paid_days else None
        )


def precompute_product_popularity(idx: GraphIndex):
    """
    Product.order_count   = how many ORDER_CONTAINS edges point to it
    Product.total_ordered_qty = total quantity ordered
    Product.plant_count   = how many plants it's available at

    WHY: "What's our most ordered product?" — instant answer.
    """
    for prod in idx.nodes_by_type.get(PRODUCT, []):
        props = prod["properties"]

        order_edges = idx.get_incoming(prod["node_id"], ORDER_CONTAINS)
        props["order_count"] = len(order_edges)
        props["total_ordered_qty"] = sum(
            float(e["properties"].get("quantity") or 0) for e in order_edges
        )

        avail_edges = idx.get_outgoing(prod["node_id"], AVAILABLE_AT)
        props["plant_count"] = len(avail_edges)


def precompute_plant_utilization(idx: GraphIndex):
    """
    Plant.order_count     = how many orders fulfilled at this plant
    Plant.product_count   = how many products available at this plant

    WHY: "Which plant handles the most orders?"
    """
    for plant in idx.nodes_by_type.get(PLANT, []):
        props = plant["properties"]

        # ORDER_FULFILLED_AT goes SalesOrder→Plant, so incoming to plant = orders
        order_edges = idx.get_incoming(plant["node_id"], ORDER_FULFILLED_AT)
        props["order_count"] = len(order_edges)

        # AVAILABLE_AT goes Product→Plant, so incoming to plant = products available there
        product_edges = idx.get_incoming(plant["node_id"], AVAILABLE_AT)
        props["product_count"] = len(product_edges)


def precompute_qty_variance(idx: GraphIndex):
    """
    ORDER_CONTAINS edge.qty_variance = confirmed_quantity - requested quantity

    WHY: Negative variance = supply shortfall. Agent can find "items with shortfalls."
    """
    for e in idx.get_edges(ORDER_CONTAINS):
        props = e["properties"]
        requested = props.get("quantity")
        confirmed = props.get("confirmed_quantity")

        if requested is not None and confirmed is not None:
            props["qty_variance"] = float(confirmed) - float(requested)
            props["has_shortfall"] = props["qty_variance"] < 0
        else:
            props["qty_variance"] = None
            props["has_shortfall"] = None


def precompute_fulfillment_rate(idx: GraphIndex):
    """
    SalesOrder.fulfillment_rate = sum(delivered_qty) / sum(ordered_qty)

    WHY: Partial delivery detection. < 1.0 means some items not fully delivered.
    """
    for so in idx.nodes_by_type.get(SALES_ORDER, []):
        props = so["properties"]

        # Total ordered qty
        order_items = idx.get_outgoing(so["node_id"], ORDER_CONTAINS)
        total_ordered = sum(float(e["properties"].get("quantity") or 0) for e in order_items)

        # Total delivered qty
        total_delivered = 0.0
        for de in idx.get_outgoing(so["node_id"], DELIVERED_BY):
            for dc in idx.get_outgoing(de["target_id"], DELIVERY_CONTAINS):
                total_delivered += float(dc["properties"].get("actual_quantity") or 0)

        if total_ordered > 0:
            props["fulfillment_rate"] = round(total_delivered / total_ordered, 3)
        else:
            props["fulfillment_rate"] = None


# ─── Master precompute runner ────────────────────────────────────────────────

def run_all_precomputes(nodes_by_type: dict[str, list[dict]], edges: list[dict]):
    """
    Run all precomputes in dependency order.
    Modifies nodes and edges in-place.

    Order matters:
      1. Journal entry flags (is_paid) — needed by customer aggregates
      2. Cycle times — independent
      3. Aggregations — depend on flags
      4. Edge-level computations — independent
    """
    idx = GraphIndex(nodes_by_type, edges)

    # Phase 1: Status flags
    precompute_journal_entry_flags(idx)

    # Phase 2: Cycle times (per-entity)
    precompute_sales_order_cycle_times(idx)
    precompute_delivery_cycle_times(idx)
    precompute_journal_entry_cycle_times(idx)
    precompute_order_to_cash(idx)

    # Phase 3: Aggregations (depend on Phase 1)
    precompute_customer_aggregates(idx)
    precompute_product_popularity(idx)
    precompute_plant_utilization(idx)

    # Phase 4: Edge-level computations
    precompute_qty_variance(idx)
    precompute_fulfillment_rate(idx)

    return idx
