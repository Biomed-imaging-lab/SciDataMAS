"""
dag_viz.py

Interactive DAG visualization for M4 typed graphs.
Renders to an HTML file that opens in the browser.

Usage
-----
    from dag_viz import visualize_dag

    dag = convert_to_DAG(nodes, edges)
    visualize_dag(dag, path="dag.html")   # opens in browser automatically
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pyvis.network import Network

# ── re-use your existing data classes ────────────────────────────────────────
# (paste or import DAGNode, DAGEdge, DAG from your module)

# ── colour palette: node_type → (background, border, text) ──────────────────
# Light fill + dark border so labels are readable in both directions.
NODE_STYLES: dict[str, dict] = {
    "Entity": {"color": "#9FE1CB", "border": "#0F6E56", "font": "#085041"},
    "Process": {"color": "#D3D1C7", "border": "#5F5E5A", "font": "#2C2C2A"},
    "Capture": {"color": "#FAC775", "border": "#854F0B", "font": "#412402"},
    "Signal": {"color": "#CECBF6", "border": "#3C3489", "font": "#26215C"},
    "Derivative": {"color": "#F5C4B3", "border": "#993C1D", "font": "#4A1B0C"},
    "Condition": {"color": "#B5D4F4", "border": "#185FA5", "font": "#042C53"},
    "Hardware": {"color": "#C0DD97", "border": "#3B6D11", "font": "#173404"},
    "Software": {"color": "#EAF3DE", "border": "#639922", "font": "#3B6D11"},
    "Provenance": {"color": "#F4C0D1", "border": "#993556", "font": "#4B1528"},
    # fallback for unknown types
    "_unknown": {"color": "#F1EFE8", "border": "#888780", "font": "#2C2C2A"},
}

EDGE_COLOR = "#888780"
ARROW_COLOR = "#5F5E5A"


def _node_style(node_type: str) -> dict:
    return NODE_STYLES.get(node_type, NODE_STYLES["_unknown"])


def _node_label(node) -> str:
    """Multi-line label: type tag + human-readable name."""
    if hasattr(node, "node_type"):
        tag = f"[{node.node_type}]"
    else:
        tag = f"[{node.node_id}]"
    return f"{tag}\n{node.name}"


def _node_title(node) -> str:
    """HTML tooltip shown on hover."""
    if hasattr(node, "node_type"):
        lines = [
            f"<b>{node.name}</b>",
            f"<i>{node.node_type}</i>",
            f"<hr/>",
            f"{node.description}",
        ]
    else:
        lines = [
            f"<b>{node.name}</b>",
            f"<hr/>",
            f"{node.description}",
        ]
    if hasattr(node, "agent") and node.agent:
        lines.append(f"<br/><b>Agent:</b> {node.agent}")
    if hasattr(node, "is_external") and node.is_external:
        lines.append("<br/><b>⚠ External data</b>")
    return "".join(lines)


def visualize_dag(
    dag,  # DAG instance
    path: str | Path = "dag.html",
    title: str = "M4 Experimental DAG",
    height: str = "800px",
    width: str = "100%",
    physics: bool = True,
    open_browser: bool = True,
) -> Path:
    """
    Render the DAG as an interactive HTML graph and save it.

    Parameters
    ----------
    dag          : DAG instance from convert_to_DAG().
    path         : output HTML file path.
    title        : page title shown in the browser tab.
    height       : canvas height (CSS string).
    width        : canvas width (CSS string).
    physics      : enable force-directed layout. Set False for static layout.
    open_browser : automatically open the file in the default browser.

    Returns
    -------
    Path to the saved HTML file.
    """
    net = Network(
        height=height,
        width=width,
        directed=True,
        notebook=False,
        bgcolor="#FAFAF8",
        font_color="#2C2C2A",
    )

    # ── physics options ───────────────────────────────────────────────────────
    if physics:
        net.set_options("""
        {
          "physics": {
            "solver": "hierarchicalRepulsion",
            "hierarchicalRepulsion": {
              "nodeDistance": 160,
              "springLength": 120,
              "springConstant": 0.04,
              "damping": 0.1
            },
            "minVelocity": 0.75,
            "stabilization": { "iterations": 200 }
          },
          "layout": {
            "hierarchical": {
              "enabled": true,
              "direction": "UD",
              "sortMethod": "directed",
              "levelSeparation": 150,
              "nodeSpacing": 180
            }
          },
          "edges": {
            "smooth": { "type": "cubicBezier", "forceDirection": "vertical" },
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.8 } }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": true,
            "keyboard": true
          }
        }
        """)
    else:
        net.set_options("""
        {
          "physics": { "enabled": false },
          "edges": {
            "smooth": { "type": "cubicBezier" },
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.8 } }
          },
          "interaction": { "hover": true, "tooltipDelay": 100 }
        }
        """)

    # ── nodes ─────────────────────────────────────────────────────────────────
    for node_id, node in dag.nodes.items():
        if hasattr(node, "node_type"):
            style = _node_style(node.node_type)
        else:
            style = NODE_STYLES["Entity"]

        net.add_node(
            node_id,
            label=_node_label(node),
            title=_node_title(node),
            color={
                "background": style["color"],
                "border": style["border"],
                "highlight": {"background": style["color"], "border": "#000000"},
                "hover": {"background": style["color"], "border": "#000000"},
            },
            font={"color": style["font"], "size": 13, "face": "monospace"},
            borderWidth=2,
            borderWidthSelected=3,
            shape="box",
            margin={"top": 8, "bottom": 8, "left": 10, "right": 10},
        )

    # ── edges ─────────────────────────────────────────────────────────────────
    for edge in dag.edges:
        if hasattr(dag.nodes[edge.source], "node_type"):
            src_type = (
                dag.nodes[edge.source].node_type if edge.source in dag.nodes else ""
            )
        else:
            src_type = "Entity"
        # softer colour for annotation edges (Condition, Hardware, Software, Provenance)
        is_annotation = src_type in ("Condition", "Hardware", "Software", "Provenance")
        net.add_edge(
            edge.source,
            edge.target,
            color={
                "color": "#B4B2A9" if is_annotation else EDGE_COLOR,
                "highlight": "#000000",
            },
            width=1 if is_annotation else 2,
            dashes=is_annotation,  # dashed for annotation edges
            arrows="to",
        )

    # ── legend ────────────────────────────────────────────────────────────────
    # Inject a floating legend into the generated HTML
    legend_html = _build_legend_html()

    # ── save ──────────────────────────────────────────────────────────────────
    out = Path(path)
    net.save_graph(str(out))

    # Inject legend and title into the saved HTML
    html = out.read_text(encoding="utf-8")
    html = html.replace("<title>", f"<title>{title} — ", 1)
    html = html.replace("</body>", legend_html + "\n</body>", 1)
    out.write_text(html, encoding="utf-8")

    print(f"DAG saved → {out.resolve()}")

    if open_browser:
        import webbrowser

        webbrowser.open(out.resolve().as_uri())

    return out


def _build_legend_html() -> str:
    items = "\n".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
        f'<div style="width:14px;height:14px;border-radius:3px;'
        f'background:{v["color"]};border:2px solid {v["border"]}"></div>'
        f'<span style="font-size:12px;color:#2C2C2A">{k}</span>'
        f"</div>"
        for k, v in NODE_STYLES.items()
        if k != "_unknown"
    )
    dashed_note = (
        '<div style="margin-top:8px;font-size:11px;color:#888780">'
        "--- dashed = annotation edge (Condition, Hardware, Software, Provenance)"
        "</div>"
    )
    return f"""
<div style="
  position:fixed;bottom:20px;left:20px;
  background:rgba(255,255,255,0.95);
  border:1px solid #D3D1C7;border-radius:8px;
  padding:12px 16px;z-index:9999;
  box-shadow:0 2px 8px rgba(0,0,0,0.12);
  font-family:monospace;
">
  <div style="font-weight:600;font-size:13px;margin-bottom:8px;color:#2C2C2A">
    Node types
  </div>
  {items}
  {dashed_note}
</div>
"""
