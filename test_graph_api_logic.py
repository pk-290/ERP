
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from graph_rag.kuzu_store import get_connection, get_database, NODE_SCHEMAS, REL_SCHEMAS

def test_graph_logic():
    try:
        db = get_database()
        conn = get_connection(db)
        
        print("--- Testing Node Fetching ---")
        for table_name in list(NODE_SCHEMAS.keys())[:2]: # Test first two tables
            print(f"Table: {table_name}")
            res = conn.execute(f"MATCH (n:{table_name}) RETURN n LIMIT 1")
            if res.has_next():
                node = res.get_next()[0]
                print(f"Node type: {type(node)}")
                print(f"Node content: {node}")
                try:
                    print(f"Node items: {node.items()}")
                except Exception as e:
                    print(f"Node.items() failed: {e}")
                
                try:
                    print(f"Node['node_id']: {node['node_id']}")
                except Exception as e:
                    print(f"node['node_id'] failed: {e}")
            else:
                print(f"No nodes found for {table_name}")
        
        print("\n--- Testing Edge Fetching ---")
        for rel_name in list(REL_SCHEMAS.keys())[:2]: # Test first two rels
            print(f"Relationship: {rel_name}")
            res = conn.execute(f"MATCH (a)-[r:{rel_name}]->(b) RETURN a.node_id, b.node_id, r LIMIT 1")
            if res.has_next():
                row = res.get_next()
                print(f"Row content: {row}")
                src_id, dst_id, rel = row
                print(f"Rel type: {type(rel)}")
                print(f"Rel content: {rel}")
            else:
                print(f"No edges found for {rel_name}")
                
    except Exception as e:
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    test_graph_logic()
