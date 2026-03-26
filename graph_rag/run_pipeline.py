#!/usr/bin/env python3
"""
Run the graph RAG preprocessing pipeline.

Usage:
    python -m graph_rag.run_pipeline
"""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_rag.graph_builder import run_pipeline


def main():
    G, graph_data = run_pipeline(include_raw_in_graph=False)

    # Print some sample queries to validate the graph
    print("\n" + "=" * 60)
    print("VALIDATION SAMPLES")
    print("=" * 60)

    # Sample 1: Pick a customer and show their order chain
    customers = graph_data["indexes"]["by_type"].get("Customer", [])
    if customers:
        cust_id = customers[0]
        cust = graph_data["nodes"][cust_id]
        print(f"\n📋 Sample Customer: {cust['properties'].get('name')}")
        print(f"   Orders: {cust['properties'].get('total_orders')}")
        print(f"   Total Billed: {cust['properties'].get('total_billed_amount')} INR")
        print(f"   Outstanding: {cust['properties'].get('outstanding_amount')} INR")
        print(f"   Avg Days to Pay: {cust['properties'].get('avg_days_to_pay')}")

    # Sample 2: Pick a product
    products = graph_data["indexes"]["by_type"].get("Product", [])
    if products:
        prod_id = products[0]
        prod = graph_data["nodes"][prod_id]
        print(f"\n📦 Sample Product: {prod['properties'].get('description')}")
        print(f"   Order Count: {prod['properties'].get('order_count')}")
        print(f"   Total Ordered Qty: {prod['properties'].get('total_ordered_qty')}")
        print(f"   Available at Plants: {prod['properties'].get('plant_count')}")

    # Sample 3: Pick an order and show cycle
    orders = graph_data["indexes"]["by_type"].get("SalesOrder", [])
    if orders:
        so_id = orders[0]
        so = graph_data["nodes"][so_id]
        print(f"\n🛒 Sample Sales Order: {so_id}")
        print(f"   Amount: {so['properties'].get('total_net_amount')} {so['properties'].get('currency')}")
        print(f"   Delivery Status: {so['properties'].get('delivery_status')}")
        print(f"   Days to Deliver: {so['properties'].get('days_to_deliver')}")
        print(f"   Fulfillment Rate: {so['properties'].get('fulfillment_rate')}")
        print(f"   O2C Days: {so['properties'].get('order_to_cash_days')}")

    # Sample 4: Edge count summary
    print(f"\n🔗 Edge Distribution:")
    for etype, count in sorted(graph_data["metadata"]["edge_types"].items()):
        print(f"   {etype}: {count}")

    # Sample 5: Journal entry payment status
    je_nodes = graph_data["indexes"]["by_type"].get("JournalEntry", [])
    paid = sum(1 for jid in je_nodes if graph_data["nodes"][jid]["properties"].get("is_paid"))
    unpaid = len(je_nodes) - paid
    print(f"\n💰 Payment Status:")
    print(f"   Paid journal entries: {paid}")
    print(f"   Unpaid journal entries: {unpaid}")


if __name__ == "__main__":
    main()
