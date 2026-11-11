"""
plot_dendrogram.py

Draws a dendrogram with colored spans and name labels for every cluster
produced by flat_cut().

Main entry point
----------------
    plot_labeled_dendrogram(
        linkage_matrix   = Z,
        node_info        = node_info,       # from build_cluster_descriptions()
        model            = model,           # fitted AgglomerativeClustering
        n_clusters       = 6,
        field_names      = field_names,
        path_to_save     = "dendrogram.png",
    )
"""

from __future__ import annotations

from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from scipy.cluster.hierarchy import dendrogram
import math

# reuse flat_cut from the file you already have
from tree_labeling import flat_cut


DISTANCE_LABELS = {
    0.00: "Identical",
    0.06: "Almost identical",
    0.26: "Very similar",
    0.58: "Moderately similar",
    1.00: "Weakly related (same domain)",
    1.48: "Barely related (distant association)",
    2.00: "Unrelated / orthogonal",
    3.00: "Opposing or contradictory",
    4.00: "Strongly opposite",
}


# ── Colour palette (same logic as plots.py) ──────────────────────────────────

_PALETTE_HEX = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B3", "#937860", "#DA8BC3", "#8C8C8C",
    "#CCB974", "#64B5CD", "#2E8B57", "#FF6347",
]
 
 
def _palette(n: int) -> List[str]:
    return [_PALETTE_HEX[i % len(_PALETTE_HEX)] for i in range(n)]
 
 
def _build_leaf_to_x(ddata: dict) -> Dict[int, float]:
    leaves = ddata["leaves"]
    return {leaf: 5 + 10 * i for i, leaf in enumerate(leaves)}
 
 
def _cluster_x_span(
    cluster_leaves: List[str],
    field_names: List[str],
    leaf_to_x: Dict[int, float],
) -> tuple[float, float]:
    name_to_idx = {name: i for i, name in enumerate(field_names)}
    xs = [
        leaf_to_x[name_to_idx[leaf]]
        for leaf in cluster_leaves
        if leaf in name_to_idx and name_to_idx[leaf] in leaf_to_x
    ]
    if not xs:
        return (0.0, 0.0)
    return min(xs), max(xs)
 
 
def plot_labeled_dendrogram(
    linkage_matrix: np.ndarray,
    node_info: Dict[int, Dict],
    model,
    n_clusters: int,
    field_names: List[str],
    path_to_save: str,
    title: str = "Dendrogram with flat-cut cluster labels",
    figsize: Optional[tuple] = None,
    label_y_offset: float = 0.05,
    span_bar_y_frac: float = 0.02,
    truncate_names: int = 30,
    leaf_font_size: int = 7,
    label_font_size: int = 8,
    rotate_leaves: int = 90,
    # ── new parameter ─────────────────────────────────────────────────────
    distance_labels: Optional[Dict[float, str]] = None,
    # e.g. {0.0: "Identical", 0.26: "Very similar", 1.0: "Weakly related"}
    # Keys are y-axis values (Ward distance), values are label strings.
    distance_line_color: str = "#888888",
    distance_line_style: str = "--",
    distance_line_width: float = 0.8,
    distance_label_fontsize: int = 7,
    distance_label_side: str = "right",   # "right" or "left"
) -> None:
    """
    Parameters (new ones only — all original parameters unchanged)
    -------------------------------------------------------------
    distance_labels       : Dict mapping y-axis distance → semantic label string.
                            A dashed horizontal line + text annotation is drawn
                            for every entry that falls within the visible y range.
                            Pass None to skip.
    distance_line_color   : Colour of the reference lines. Default "#888888".
    distance_line_style   : Linestyle. Default "--".
    distance_line_width   : Line width. Default 0.8.
    distance_label_fontsize: Font size for the reference line labels. Default 7.
    distance_label_side   : "right" (default) places labels at the right edge of
                            the axes; "left" places them at the left edge.
    """
    n_fields = len(field_names)
    if figsize is None:
        figsize = (max(14, n_fields * 0.38), 8)
 
    clusters     = flat_cut(node_info, model, n_clusters)
    colors       = _palette(n_clusters)
    cid_to_color = {cid: colors[i] for i, cid in enumerate(sorted(clusters))}
 
    fig, ax = plt.subplots(figsize=figsize)
 
    ddata = dendrogram(
        linkage_matrix,
        labels=field_names,
        ax=ax,
        color_threshold=0,
        above_threshold_color="#AAAAAA",
        leaf_rotation=rotate_leaves,
        leaf_font_size=leaf_font_size,
        no_plot=False,
    )
 
    for coll in ax.collections:
        coll.set_color("#AAAAAA")
    for line in ax.get_lines():
        line.set_color("#AAAAAA")
 
    leaf_to_x = _build_leaf_to_x(ddata)
 
    y_min, y_max = ax.get_ylim()
    y_range    = y_max - y_min
    bar_height = y_range * span_bar_y_frac
    bar_y      = y_min - bar_height * 1.8
    text_y     = bar_y - y_range * label_y_offset
 
    ax.set_ylim(text_y - y_range * 0.12, y_max * 1.05)
 
    # ── cluster span bars and labels ──────────────────────────────────────
    legend_patches = []
    for cid, cluster in clusters.items():
        color = cid_to_color[cid]
        x_min, x_max = _cluster_x_span(cluster["contains"], field_names, leaf_to_x)
        if x_min == x_max == 0.0:
            continue
 
        rect = mpatches.FancyBboxPatch(
            (x_min - 4, bar_y),
            width   = (x_max - x_min) + 8,
            height  = bar_height,
            boxstyle= "round,pad=0",
            linewidth=0,
            facecolor=color,
            alpha=0.85,
            zorder=5,
        )
        ax.add_patch(rect)
 
        name = cluster["name"]
        if len(name) > truncate_names:
            name = name[:truncate_names - 1] + "…"
 
        x_centre = (x_min + x_max) / 2
        ax.text(
            x_centre, text_y, name,
            ha="center", va="top",
            fontsize=label_font_size,
            color=color,
            fontweight="bold",
            rotation=0,
            clip_on=False,
            zorder=6,
        )
        legend_patches.append(mpatches.Patch(color=color, label=name))
 
    # ── distance reference lines ──────────────────────────────────────────
    if distance_labels:
        x_data_min, x_data_max = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()
 
        label_x = x_data_max if distance_label_side == "right" else x_data_min
        label_ha = "right"   if distance_label_side == "right" else "left"
 
        for dist_val, dist_text in sorted(distance_labels.items()):
            # Only draw lines that fall within the visible y range
            if not (y_lo <= dist_val <= y_hi):
                continue
 
            ax.axhline(
                y=dist_val,
                color=distance_line_color,
                linestyle=distance_line_style,
                linewidth=distance_line_width,
                zorder=2,
            )
            ax.text(
                label_x,
                dist_val,
                f"  {dist_text} ({dist_val})" if distance_label_side == "left"
                    else f"{dist_text} ({dist_val})  ",
                ha=label_ha,
                va="bottom",
                fontsize=distance_label_fontsize,
                color=distance_line_color,
                style="italic",
                clip_on=True,
                zorder=7,
            )
 
    # ── legend and titles ─────────────────────────────────────────────────
    ax.legend(
        handles=legend_patches,
        title=f"Flat cut  (k={n_clusters})",
        loc="upper right",
        bbox_to_anchor=(1.18, 1.0),
        fontsize=label_font_size,
        title_fontsize=label_font_size,
        framealpha=0.92,
    )
 
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_ylabel("Ward distance", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
 
    fig.tight_layout()
    fig.savefig(path_to_save, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[dendrogram] saved → {path_to_save}")
