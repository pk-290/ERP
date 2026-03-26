"""
Graph assembly and serialization.
Takes extracted nodes + edges, runs precomputes, builds a NetworkX graph,
and serializes to JSON for persistence and agent consumption.
"""
import json
from pathlib import Path
from datetime import datetime

import networkx as nx

from .config import OUTPUT_DIR
from .nodes import extract_all_nodes
from .edges import extract_all_edges
from .precompute import run_all_precomputes


def build_networkx_graph(nodes_by_type: dict[str, list[dict]],
                         edges: list[dict],
                         include_raw: bool = False) -> nx.DiGraph:
    """
    Build a NetworkX directed graph from extracted nodes and edges.

    Args:
        nodes_by_type: {node_type: [node_dicts]}
        edges: [edge_dicts]
        include_raw: If True, store _raw on nodes/edges (large but zero data loss)
    """
    G = nx.DiGraph()

    # Add nodes
    for ntype, nlist in nodes_by_type.items():
        for n in nlist:
            attrs = {
                "node_type": n["node_type"],
                **n["properties"],
            }
            if include_raw:
                attrs["_raw"] = n.get("_raw")
                attrs["_fks"] = n.get("_fks")
            G.add_node(n["node_id"], **attrs)

    # Add edges
    for e in edges:
        attrs = {
            "edge_type": e["edge_type"],
            **e["properties"],
        }
        if include_raw and e.get("_raw"):
            attrs["_raw"] = e["_raw"]

        # NetworkX allows only one edge between a pair in DiGraph.
        # If duplicate (same source, target), use MultiDiGraph behavior via key.
        if G.has_edge(e["source_id"], e["target_id"]):
            # Multiple edges between same pair (e.g., multiple items)
            # Store as list or use edge_type as distinguisher
            existing = G[e["source_id"]][e["target_id"]]
            if "_multi" not in existing:
                existing["_multi"] = [dict(existing)]
            existing["_multi"].append(attrs)
        else:
            G.add_edge(e["source_id"], e["target_id"], **attrs)

    return G


def serialize_graph(nodes_by_type: dict[str, list[dict]],
                    edges: list[dict],
                    output_dir: Path | None = None) -> dict:
    """
    Serialize the graph to a JSON-compatible dict and save to disk.

    Output structure:
      {
        "metadata": {...},
        "nodes": {node_id: {type, properties}},
        "edges": [{source, target, type, properties}],
        "indexes": {
          "by_type": {node_type: [node_ids]},
          "customers_by_name": {name: node_id},
          "products_by_description": {desc: node_id},
        }
      }
    """
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build the serializable structure
    graph_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "node_count": sum(len(v) for v in nodes_by_type.values()),
            "edge_count": len(edges),
            "node_types": {k: len(v) for k, v in nodes_by_type.items()},
            "edge_types": {},
        },
        "nodes": {},
        "edges": [],
        "indexes": {
            "by_type": {},
            "customers_by_name": {},
            "products_by_description": {},
            "plants_by_name": {},
        },
    }

    # Count edge types
    for e in edges:
        et = e["edge_type"]
        graph_data["metadata"]["edge_types"][et] = (
            graph_data["metadata"]["edge_types"].get(et, 0) + 1
        )

    # Serialize nodes (without _raw for the main file — save _raw separately)
    for ntype, nlist in nodes_by_type.items():
        type_ids = []
        for n in nlist:
            nid = n["node_id"]
            type_ids.append(nid)
            graph_data["nodes"][nid] = {
                "node_type": n["node_type"],
                "properties": _json_safe(n["properties"]),
            }

            # Build search indexes
            props = n["properties"]
            if ntype == "Customer" and props.get("name"):
                graph_data["indexes"]["customers_by_name"][props["name"].lower()] = nid
            elif ntype == "Product" and props.get("description"):
                graph_data["indexes"]["products_by_description"][props["description"].lower()] = nid
            elif ntype == "Plant" and props.get("name"):
                graph_data["indexes"]["plants_by_name"][props["name"].lower()] = nid

        graph_data["indexes"]["by_type"][ntype] = type_ids

    # Serialize edges
    for e in edges:
        graph_data["edges"].append({
            "source": e["source_id"],
            "target": e["target_id"],
            "edge_type": e["edge_type"],
            "properties": _json_safe(e["properties"]),
        })

    # Write main graph file
    graph_file = out_dir / "graph.json"
    with open(graph_file, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, default=str)

    # Write raw data backup (for zero data loss guarantee)
    raw_data = {
        "nodes": {
            n["node_id"]: n.get("_raw")
            for nlist in nodes_by_type.values()
            for n in nlist
        },
        "edges": [
            {"source": e["source_id"], "target": e["target_id"],
             "type": e["edge_type"], "_raw": e.get("_raw")}
            for e in edges if e.get("_raw")
        ],
    }
    raw_file = out_dir / "graph_raw_backup.json"
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2, default=str)

    print(f"Graph saved to {graph_file} ({graph_file.stat().st_size / 1024:.1f} KB)")
    print(f"Raw backup saved to {raw_file} ({raw_file.stat().st_size / 1024:.1f} KB)")

    return graph_data


def _json_safe(obj):
    """Make a dict JSON-serializable (handle sets, datetimes, etc)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ─── Main pipeline ───────────────────────────────────────────────────────────

def run_pipeline(include_raw_in_graph: bool = False) -> tuple[nx.DiGraph, dict]:
    """
    Full preprocessing pipeline:
      1. Extract all nodes from JSONL
      2. Extract all edges from FK relationships
      3. Run precomputes (derived properties)
      4. Build NetworkX graph
      5. Serialize to JSON

    Returns: (nx_graph, graph_data_dict)
    """
    print("=" * 60)
    print("GRAPH RAG PREPROCESSING PIPELINE")
    print("=" * 60)

    # Step 1: Extract nodes
    print("\n[1/5] Extracting nodes...")
    nodes_by_type = extract_all_nodes()
    for ntype, nlist in nodes_by_type.items():
        print(f"  {ntype}: {len(nlist)} nodes")

    # Step 2: Extract edges
    print("\n[2/5] Extracting edges...")
    edges = extract_all_edges(nodes_by_type)
    edge_counts: dict[str, int] = {}
    for e in edges:
        edge_counts[e["edge_type"]] = edge_counts.get(e["edge_type"], 0) + 1
    for etype, count in sorted(edge_counts.items()):
        print(f"  {etype}: {count} edges")

    # Step 3: Precomputes
    print("\n[3/5] Running precomputes...")
    idx = run_all_precomputes(nodes_by_type, edges)
    print("  ✓ Journal entry flags (is_paid)")
    print("  ✓ Cycle times (days_to_deliver, days_to_invoice, days_to_pay)")
    print("  ✓ Order-to-cash days")
    print("  ✓ Customer aggregates (total_orders, total_billed, outstanding)")
    print("  ✓ Product popularity (order_count, total_ordered_qty)")
    print("  ✓ Plant utilization (order_count, product_count)")
    print("  ✓ Quantity variance & fulfillment rate")

    # Step 4: Build NetworkX graph
    print("\n[4/5] Building NetworkX graph...")
    G = build_networkx_graph(nodes_by_type, edges, include_raw=include_raw_in_graph)
    print(f"  Nodes: {G.number_of_nodes()}")
    print(f"  Edges: {G.number_of_edges()}")
    print(f"  Connected components (undirected): {nx.number_weakly_connected_components(G)}")

    # Step 5: Serialize
    print("\n[5/5] Serializing to JSON...")
    graph_data = serialize_graph(nodes_by_type, edges)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"  Total nodes: {graph_data['metadata']['node_count']}")
    print(f"  Total edges: {graph_data['metadata']['edge_count']}")
    print("=" * 60)

    return G, graph_data
