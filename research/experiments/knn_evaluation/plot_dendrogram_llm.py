"""
plot_dendrogram_llm.py

flat_cut() and plot_labeled_dendrogram() that work exclusively with
AgglomerationResult from llm_agglomerative.py.
No sklearn AgglomerativeClustering model required.

Usage
-----
    from llm_agglomerative import llm_agglomerate
    from plot_dendrogram_llm import flat_cut, plot_labeled_dendrogram

    result = llm_agglomerate(...)

    clusters = flat_cut(result, n_clusters=6)
    plot_labeled_dendrogram(result, n_clusters=6,
                            path_to_save="dendrogram.png")
"""

from __future__ import annotations

from typing import Dict, List, Optional

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from scipy.cluster.hierarchy import dendrogram

# The dataclass lives in llm_agglomerative — import only the type.
# (If you keep everything in one file, remove this import.)
from llm_agglomerative import AgglomerationResult


# ── Palette ───────────────────────────────────────────────────────────────────

_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B3", "#937860", "#DA8BC3", "#3A7D8C",
    "#CCB974", "#64B5CD", "#2E8B57", "#FF6347",
]


def _palette(n: int) -> List[str]:
    return [_PALETTE[i % len(_PALETTE)] for i in range(n)]


# ── flat_cut ──────────────────────────────────────────────────────────────────

def flat_cut(
    result: AgglomerationResult,
    n_clusters: int,
) -> Dict[int, Dict]:
    """
    Return the node_info entries that form a flat cut of the LLM tree
    into exactly n_clusters clusters.

    Works entirely from AgglomerationResult — no sklearn model needed.

    The algorithm replays merges from the linkage matrix:
      - Start with all leaf nodes active.
      - Apply merges one by one (each merge reduces active count by 1).
      - Stop after (n_leaves - n_clusters) merges.
      - The active set at that point is the flat cut.

    Parameters
    ----------
    result     : AgglomerationResult from llm_agglomerate().
    n_clusters : desired number of clusters (1 ≤ n_clusters ≤ n_leaves).

    Returns
    -------
    Dict[cluster_id, node_info_entry] — one entry per cluster,
    with an extra key "cluster_id" added.
    """
    n_leaves = _n_leaves(result)

    if not (1 <= n_clusters <= n_leaves):
        raise ValueError(
            f"n_clusters must be in [1, {n_leaves}], got {n_clusters}."
        )

    # Start: every leaf is active
    active: set[int] = set(range(n_leaves))
    n_merges_to_apply = n_leaves - n_clusters

    # linkage_matrix rows: [left, right, distance, size]
    for k in range(n_merges_to_apply):
        left  = int(result.linkage_matrix[k, 0])
        right = int(result.linkage_matrix[k, 1])
        internal = n_leaves + k
        active.discard(left)
        active.discard(right)
        active.add(internal)

    output: Dict[int, Dict] = {}
    for cid, node_idx in enumerate(sorted(active)):
        entry = dict(result.node_info[node_idx])
        entry["cluster_id"] = cid
        output[cid] = entry

    return output


# ── Helpers for plot ──────────────────────────────────────────────────────────

def _n_leaves(result: AgglomerationResult) -> int:
    """Number of leaf nodes = number of fields."""
    return result.linkage_matrix.shape[0] + 1


def _children_array(result: AgglomerationResult) -> np.ndarray:
    """Reconstruct the (N-1, 2) children array from the linkage matrix."""
    return result.linkage_matrix[:, :2].astype(int)


def _field_names_in_order(result: AgglomerationResult) -> List[str]:
    """
    Return leaf field names ordered by their original index (0, 1, 2, …).
    Leaf nodes in node_info have indices 0 … n_leaves-1.
    """
    n_leaves = _n_leaves(result)
    return [result.node_info[i]["name"] for i in range(n_leaves)]


def _build_node_cid_set(
    result: AgglomerationResult,
    field_to_cid: Dict[str, int],
) -> Dict[int, set]:
    """
    For every node (leaf and internal), compute the set of cluster-ids
    among its descendant leaves.  Used to colour dendrogram links.
    """
    n_leaves  = _n_leaves(result)
    children  = _children_array(result)
    field_names = _field_names_in_order(result)

    node_cid_set: Dict[int, set] = {}
    for i, fname in enumerate(field_names):
        node_cid_set[i] = {field_to_cid.get(fname, -1)}

    for k, (left, right) in enumerate(children):
        internal = n_leaves + k
        node_cid_set[internal] = node_cid_set[left] | node_cid_set[right]

    return node_cid_set


def _field_to_cluster(clusters: Dict[int, Dict]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for cid, info in clusters.items():
        for fname in info["contains"]:
            result[fname] = cid
    return result


# ── plot_labeled_dendrogram ───────────────────────────────────────────────────

def plot_labeled_dendrogram(
    result: AgglomerationResult,
    n_clusters: int,
    path_to_save: str,
    title: str = "Dendrogram with flat-cut cluster labels",
    figsize: Optional[tuple] = None,
    leaf_font_size: int = 7,
    label_font_size: int = 8,
    truncate_names: int = 28,
) -> None:
    """
    Draw a dendrogram from AgglomerationResult with coloured links and
    labelled cluster bands below the leaf axis.

    Parameters
    ----------
    result        : AgglomerationResult from llm_agglomerate().
    n_clusters    : number of flat clusters to highlight.
    path_to_save  : output file path (.png / .pdf / .svg).
    title         : figure title.
    figsize       : (width, height) in inches. Auto-computed if None.
    leaf_font_size: font size for field name labels on the x-axis.
    label_font_size: font size for cluster name labels inside the bands.
    truncate_names: clip cluster names longer than this many characters.
    """
    n_leaves    = _n_leaves(result)
    field_names = _field_names_in_order(result)

    if figsize is None:
        figsize = (max(16, n_leaves * 0.42), 12)

    # ── 1. Build flat clusters ────────────────────────────────────────────
    clusters     = flat_cut(result, n_clusters)
    colors       = _palette(n_clusters)
    sorted_cids  = sorted(clusters.keys())
    cid_to_color = {cid: colors[i] for i, cid in enumerate(sorted_cids)}
    field_to_cid = _field_to_cluster(clusters)

    # ── 2. Per-node cluster-id sets (for link colouring) ─────────────────
    node_cid_set = _build_node_cid_set(result, field_to_cid)

    def link_color(node_id: int) -> str:
        s = node_cid_set.get(node_id, set())
        if len(s) == 1:
            return cid_to_color.get(next(iter(s)), "#CCCCCC")
        return "#CCCCCC"

    # ── 3. Draw dendrogram ────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize)

    ddata = dendrogram(
        result.linkage_matrix,
        labels=field_names,
        ax=ax,
        color_threshold=0,
        above_threshold_color="#CCCCCC",
        link_color_func=lambda nid: link_color(nid),
        leaf_rotation=90,
        leaf_font_size=leaf_font_size,
    )

    # Colour x-tick labels by their cluster
    for tick, leaf_idx in zip(ax.get_xticklabels(), ddata["leaves"]):
        fname = field_names[leaf_idx]
        cid   = field_to_cid.get(fname, -1)
        tick.set_color(cid_to_color.get(cid, "#333333"))

    # ── 4. Colour bands below leaf labels ─────────────────────────────────
    ax.set_clip_on(False)
    x_min_data, x_max_data = ax.get_xlim()
    x_range = x_max_data - x_min_data

    # scipy places leaf i at x = 5 + 10*i in the order ddata["leaves"]
    leaf_order = ddata["leaves"]
    l2x = {leaf: 5 + 10 * pos for pos, leaf in enumerate(leaf_order)}

    # Group consecutive leaves that share a cluster
    spans: List[tuple] = []   # (cid, x_left_data, x_right_data)
    cur_cid    = field_to_cid.get(field_names[leaf_order[0]], -1)
    span_start = l2x[leaf_order[0]]
    prev_x     = span_start

    for leaf_idx in leaf_order[1:]:
        fname = field_names[leaf_idx]
        cid   = field_to_cid.get(fname, -1)
        if cid != cur_cid:
            spans.append((cur_cid, span_start, prev_x))
            cur_cid    = cid
            span_start = l2x[leaf_idx]
        prev_x = l2x[leaf_idx]
    spans.append((cur_cid, span_start, prev_x))

    def ax_x(data_x: float) -> float:
        return (data_x - x_min_data) / x_range

    BAND = 0.030   # band height as fraction of axes height
    GAP  = 0.005   # gap between x-axis and band

    for cid, x0_d, x1_d in spans:
        color = cid_to_color.get(cid, "#CCCCCC")
        ax0   = ax_x(x0_d - 4.5)
        ax1   = ax_x(x1_d + 4.5)
        by0   = -(GAP + BAND)

        rect = mpatches.FancyBboxPatch(
            (ax0, by0),
            width     = max(ax1 - ax0, 0.001),
            height    = BAND,
            transform = ax.transAxes,
            boxstyle  = "round,pad=0.003",
            linewidth = 0,
            facecolor = color,
            alpha     = 0.92,
            clip_on   = False,
            zorder    = 10,
        )
        ax.add_patch(rect)

        name = clusters[cid]["name"] if cid in clusters else ""
        if len(name) > truncate_names:
            name = name[:truncate_names - 1] + "…"

        ax.text(
            (ax0 + ax1) / 2,
            by0 + BAND / 2,
            name,
            transform  = ax.transAxes,
            ha         = "center",
            va         = "center",
            fontsize   = label_font_size,
            fontweight = "bold",
            color      = "white",
            clip_on    = False,
            zorder     = 11,
        )

    # ── 5. Legend ─────────────────────────────────────────────────────────
    patches = [
        mpatches.Patch(
            color=cid_to_color[cid],
            label=(
                clusters[cid]["name"][:42] + "…"
                if len(clusters[cid]["name"]) > 42
                else clusters[cid]["name"]
            ),
        )
        for cid in sorted_cids
        if cid in clusters
    ]
    ax.legend(
        handles        = patches,
        title          = f"Flat cut  (k = {n_clusters})",
        loc            = "upper left",
        bbox_to_anchor = (1.01, 1.0),
        fontsize       = label_font_size,
        title_fontsize = label_font_size + 1,
        framealpha     = 0.95,
        edgecolor      = "#CCCCCC",
    )

    # ── 6. Styling ────────────────────────────────────────────────────────
    ax.set_title(title, fontsize=12, pad=12)
    ax.set_ylabel("Cosine distance", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", which="both", length=0)

    fig.subplots_adjust(bottom=0.24, right=0.80)
    fig.savefig(path_to_save, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[dendrogram] saved → {path_to_save}")
