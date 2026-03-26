"""
Interactive graph visualization using pyvis.
Generates an HTML file you can open in a browser to explore the graph.
"""
import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def build_visualization():
    from pyvis.network import Network

    with open(OUTPUT_DIR / "graph.json", "r") as f:
        g = json.load(f)

    # Color scheme per node type
    COLORS = {
        "Customer": "#e74c3c",       # red
        "Product": "#3498db",         # blue
        "Plant": "#2ecc71",           # green
        "SalesOrder": "#f39c12",      # orange
        "Delivery": "#9b59b6",        # purple
        "BillingDocument": "#1abc9c", # teal
        "JournalEntry": "#e67e22",    # dark orange
    }

    SIZES = {
        "Customer": 35,
        "Plant": 25,
        "Product": 15,
        "SalesOrder": 12,
        "Delivery": 10,
        "BillingDocument": 10,
        "JournalEntry": 8,
    }

    EDGE_COLORS = {
        "PLACED_ORDER": "#e74c3c",
        "ORDER_CONTAINS": "#f39c12",
        "ORDER_FULFILLED_AT": "#2ecc71",
        "DELIVERED_BY": "#9b59b6",
        "DELIVERY_CONTAINS": "#9b59b6",
        "INVOICED_BY": "#1abc9c",
        "POSTED_AS": "#e67e22",
        "CLEARED_BY": "#27ae60",
        "AVAILABLE_AT": "#bdc3c7",
        "CANCELS": "#c0392b",
        "CUSTOMER_BILLED": "#e74c3c",
        "ORDER_INVOICED_BY": "#1abc9c",
    }

    # --- Build a FILTERED version (skip AVAILABLE_AT which has 3036 edges) ---
    # Full graph is too dense. Show the O2C flow + a sample of product-plant links.

    net = Network(
        height="900px",
        width="100%",
        directed=True,
        bgcolor="#1a1a2e",
        font_color="white",
        select_menu=True,
        filter_menu=True,
    )

    net.barnes_hut(
        gravity=-8000,
        central_gravity=0.3,
        spring_length=150,
        spring_strength=0.01,
        damping=0.09,
    )

    # Track which nodes to include (only those with O2C edges, not AVAILABLE_AT)
    included_nodes = set()

    # Add edges (skip AVAILABLE_AT for clarity — it's 3036 edges of product↔plant)
    filtered_edges = [
        e for e in g["edges"]
        if e["edge_type"] != "AVAILABLE_AT"
    ]

    for e in filtered_edges:
        included_nodes.add(e["source"])
        included_nodes.add(e["target"])

    # Add nodes
    for nid in included_nodes:
        if nid not in g["nodes"]:
            # Edge target might not exist as a node (e.g., clearing doc reference)
            net.add_node(nid, label=nid.split(":")[-1], size=6, color="#95a5a6",
                        title=f"Referenced: {nid}")
            continue

        node = g["nodes"][nid]
        ntype = node["node_type"]
        props = node["properties"]

        # Build label
        if ntype == "Customer":
            label = props.get("name", nid)[:20]
        elif ntype == "Product":
            label = (props.get("description") or props.get("id", ""))[:20]
        elif ntype == "Plant":
            label = props.get("name", nid)[:20]
        elif ntype == "SalesOrder":
            label = f"SO:{props.get('id', '')}"
        elif ntype == "Delivery":
            label = f"DL:{props.get('id', '')}"
        elif ntype == "BillingDocument":
            label = f"BL:{props.get('id', '')}"
        elif ntype == "JournalEntry":
            label = f"JE:{props.get('id', '')}"
        else:
            label = nid.split(":")[-1]

        # Build tooltip
        tooltip_lines = [f"<b>{ntype}: {props.get('id', nid)}</b>", ""]
        for k, v in props.items():
            if k.startswith("_") or v is None:
                continue
            tooltip_lines.append(f"{k}: {v}")
        tooltip = "<br>".join(tooltip_lines)

        net.add_node(
            nid,
            label=label,
            size=SIZES.get(ntype, 10),
            color=COLORS.get(ntype, "#95a5a6"),
            title=tooltip,
            group=ntype,
        )

    # Add edges
    for e in filtered_edges:
        etype = e["edge_type"]
        edge_props = e.get("properties", {})

        # Edge tooltip
        tip_lines = [f"<b>{etype}</b>"]
        for k, v in edge_props.items():
            if k.startswith("_") or v is None:
                continue
            tip_lines.append(f"{k}: {v}")
        tooltip = "<br>".join(tip_lines)

        net.add_edge(
            e["source"],
            e["target"],
            title=tooltip,
            color=EDGE_COLORS.get(etype, "#7f8c8d"),
            label=etype.replace("_", " ").title() if etype not in ("CUSTOMER_BILLED",) else "",
            width=2 if etype in ("PLACED_ORDER", "CUSTOMER_BILLED") else 1,
            arrows="to",
        )

    # Add legend as a note
    legend_html = """
    <div style="position:fixed;top:10px;left:10px;background:#16213e;padding:15px;border-radius:8px;z-index:1000;font-family:monospace;color:white;">
        <b>ERP Knowledge Graph</b><br><br>
        <span style="color:#e74c3c">● Customer</span><br>
        <span style="color:#3498db">● Product</span><br>
        <span style="color:#2ecc71">● Plant</span><br>
        <span style="color:#f39c12">● Sales Order</span><br>
        <span style="color:#9b59b6">● Delivery</span><br>
        <span style="color:#1abc9c">● Billing Doc</span><br>
        <span style="color:#e67e22">● Journal Entry</span><br>
        <br>
        <small>Nodes: """ + str(len(included_nodes)) + """ | Edges: """ + str(len(filtered_edges)) + """</small><br>
        <small>(AVAILABLE_AT edges hidden for clarity)</small>
    </div>
    """

    out_file = str(OUTPUT_DIR / "graph_visual.html")
    net.write_html(out_file)

    # Inject legend into HTML
    with open(out_file, "r") as f:
        html = f.read()
    html = html.replace("</body>", legend_html + "</body>")
    with open(out_file, "w") as f:
        f.write(html)

    print(f"Visualization saved to: {out_file}")
    print(f"  Nodes shown: {len(included_nodes)}")
    print(f"  Edges shown: {len(filtered_edges)} (AVAILABLE_AT hidden)")
    print(f"\nOpen in browser: file://{out_file}")
    return out_file


if __name__ == "__main__":
    build_visualization()
