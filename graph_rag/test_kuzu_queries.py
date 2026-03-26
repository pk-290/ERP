"""
Test script to verify Kuzu queries for ERP intelligence layer.
Executes 4 test cases inspired by docs/erp_ai_test_cases.md.
"""
import sys
import os

# Add parent directory to sys.path to allow imports from graph_rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_rag.kuzu_query import run_cypher

def test_o2c_verification():
    print("\n[Test Case 1] Multi-hop O2C Verification")
    print("Goal: Trace a Sales Order through to a cleared Journal Entry.")
    query = """
    MATCH (c:Customer)-[:PLACED_ORDER]->(so:SalesOrder)-[:DELIVERED_BY]->(d:Delivery)-[:INVOICED_BY]->(bd:BillingDocument)-[:POSTED_AS]->(je:JournalEntry)
    RETURN c.name, so.node_id, d.node_id, bd.node_id, je.node_id, je.is_paid
    LIMIT 3
    """
    result = run_cypher(query)
    print(result)

def test_on_time_delivery():
    print("\n[Test Case 2] On-Time Delivery Analysis")
    print("Goal: Find orders where delivery was later than requested.")
    query = """
    MATCH (so:SalesOrder)-[:DELIVERED_BY]->(d:Delivery)
    WHERE d.actual_goods_movement_date > so.requested_delivery_date
    RETURN so.node_id, so.requested_delivery_date, d.actual_goods_movement_date
    LIMIT 3
    """
    result = run_cypher(query)
    print(result)

def test_cancelled_revenue():
    print("\n[Test Case 3] Cancelled Revenue Impact")
    print("Goal: Calculate total revenue of cancelled billing documents.")
    query = """
    MATCH (bd:BillingDocument)
    WHERE bd.is_cancelled = 'true'
    RETURN sum(CAST(bd.total_net_amount AS DOUBLE)) as cancelled_revenue, count(bd) as count
    """
    result = run_cypher(query)
    print(result)

def test_product_substitution():
    print("\n[Test Case 4] Product Group Substitution")
    print("Goal: Find alternative products in the same group.")
    # We find groups that have more than one product
    query = """
    MATCH (p:Product)
    WITH p.product_group as pg, collect(p.description) as alternatives
    WHERE size(alternatives) > 1
    RETURN pg, alternatives
    LIMIT 3
    """
    result = run_cypher(query)
    print(result)

if __name__ == "__main__":
    print("🚀 Starting Kuzu Query Test Cases...")
    test_o2c_verification()
    test_on_time_delivery()
    test_cancelled_revenue()
    test_product_substitution()
    print("\n✅ All tests completed.")
