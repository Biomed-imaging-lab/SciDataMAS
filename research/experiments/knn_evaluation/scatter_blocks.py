"""
scatter_blocks.py

Interactive 2D scatter plot of metadata fields coloured by their generation block.

Reduces field embeddings to 2D via UMAP (preferred) or PCA (fallback),
then renders with Plotly so you can hover, zoom, and pan.

Input
-----
Takes the output of MDGenerationFlow directly:
    md_fields_per_block : Dict[str, MDGeneration]
        Keys  = block short_name strings
        Values = MDGeneration dicts with "md_schema" key

Embeddings are computed from "field_name: description" strings using
your real embed function, or a mockup if none is provided.

Usage
-----
    from scatter_blocks import plot_fields_scatter

    # after running the workflow:
    result = flow.workflow.invoke({"users_task": query})

    plot_fields_scatter(
        md_fields_per_block = result["md_fields_per_block"],
        embed_fn            = your_embed_fn,   # (List[str]) -> np.ndarray
        save_html           = "scatter.html",  # optional
    )
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import numpy as np

from eval.md_classes import MDField, DataStep

import numpy as np
from scipy.stats import chi2

try:
    import plotly.graph_objects as go
    import plotly.express as px

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    print("WARNING: plotly not installed. Run: pip install plotly")

try:
    import umap

    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False

from sklearn.decomposition import PCA

_PALETTE = [
    "#4C72B0",  # steel blue
    "#DD8452",  # burnt orange
    "#55A868",  # medium green
    "#C44E52",  # crimson
    "#8172B3",  # slate purple
    "#937860",  # warm brown
    "#DA8BC3",  # dusty pink
    "#3A7D8C",  # teal
    "#CCB974",  # khaki gold
    "#64B5CD",  # sky blue
    "#2E8B57",  # sea green
    "#FF6347",  # tomato
    "#9467BD",  # medium purple
    "#8C564B",  # sienna
    "#E377C2",  # orchid
    "#7F7F7F",  # mid grey
    "#BCBD22",  # olive yellow
    "#17BECF",  # cyan
    "#AEC7E8",  # pale blue
    "#FFBB78",  # peach
    "#1B4F8A",  # dark navy blue
    "#B5451B",  # rust red
    "#1A6B3C",  # forest green
    "#7B1C1C",  # dark maroon
    "#4A3A7A",  # deep indigo
    "#5C4033",  # dark mocha
    "#A0306A",  # raspberry
    "#0D5C6E",  # deep teal
    "#8A7A00",  # dark gold
    "#1F6F8B",  # denim blue
    "#D4A017",  # amber
    "#C0392B",  # alizarin red
    "#6C3483",  # grape
    "#BA4A00",  # dark orange
    "#148F77",  # jade
    "#424242",  # charcoal
    "#7D6608",  # dark olive
    "#0E6655",  # dark cyan-green
    "#6E2C00",  # dark sienna
    "#1A5276",  # prussian blue
]


def _palette(n: int) -> List[str]:
    return [_PALETTE[i % len(_PALETTE)] for i in range(n)]


# ── Embedding mockup ──────────────────────────────────────────────────────────


def _embed_mockup(strings: List[str]) -> np.ndarray:
    """Random unit-norm embeddings. Replace with your real function."""
    D = 128
    rng = np.random.default_rng(abs(hash(tuple(strings[:3]))) % (2**31))
    raw = rng.standard_normal((len(strings), D)).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return raw / np.maximum(norms, 1e-9)


# ── Dimensionality reduction ──────────────────────────────────────────────────


def _reduce_to_2d(
    embeddings: np.ndarray,
    method: str = "auto",
    umap_n_neighbors: int = 10,
    umap_min_dist: float = 0.1,
    random_state: int = 42,
) -> np.ndarray:
    """
    Reduce (N, D) embeddings to (N, 2).

    method : "umap" | "pca" | "auto"
             "auto" uses UMAP if available, else PCA.
    """
    use_umap = (method == "auto" and HAS_UMAP) or method == "umap"

    if use_umap:
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=min(umap_n_neighbors, len(embeddings) - 1),
            min_dist=umap_min_dist,
            metric="cosine",
            random_state=random_state,
        )
        coords = reducer.fit_transform(embeddings)
        method_used = "UMAP"
    else:
        reducer = PCA(n_components=2, random_state=random_state)
        coords = reducer.fit_transform(embeddings)
        method_used = "PCA"

    print(
        f"  Dimensionality reduction: {method_used} "
        f"({embeddings.shape[1]}D → 2D, {len(embeddings)} points)"
    )
    return coords.astype(np.float32), method_used


# ── Data extraction ───────────────────────────────────────────────────────────


def _extract_fields(
    md_fields_per_block: Dict[str, Dict[str, MDField]],
    md_fields_indexes: Dict[str, Dict[str, int]],
) -> tuple[List[str], List[str], List[str], List[str]]:
    """
    Flatten md_fields_per_block into parallel lists.

    Returns (field_names, descriptions, block_names, embed_strings)
    """
    field_names: List[str] = []
    descriptions: List[str] = []
    block_names: List[str] = []
    fields_ids: List[str] = []

    for block_short_name, fields_dict in md_fields_per_block.items():
        for fname, fmeta in fields_dict.items():
            field_names.append(fname)
            descriptions.append(fmeta.descr)
            block_names.append(block_short_name)
            fields_ids.append(md_fields_indexes[block_short_name][fname])

    return field_names, descriptions, block_names, fields_ids


# ── Main plot function ────────────────────────────────────────────────────────


def plot_fields_scatter(
    md_fields_per_block: Dict,
    md_fields_ids: Dict[str, Dict[str, int]],
    embed_fn: Optional[Callable] = None,
    reduction_method: str = "auto",
    umap_n_neighbors: int = 10,
    umap_min_dist: float = 0.10,
    save_html: Optional[str] = None,
    title: str = "Metadata fields — 2D embedding by block",
    point_size: int = 10,
    show: bool = True,
    random_state: int = 42,
) -> "go.Figure":
    """
    Build and display an interactive 2D scatter plot of metadata fields.

    Parameters
    ----------
    md_fields_per_block : Dict[block_name, MDGeneration]
        Direct output of MDGenerationFlow state["md_fields_per_block"].
    embed_fn            : Callable (List[str]) -> np.ndarray (N, D), L2-normalised.
                          If None, a random mockup is used.
    reduction_method    : "auto" | "umap" | "pca".
    umap_n_neighbors    : UMAP neighbours parameter (lower = more local).
    umap_min_dist       : UMAP min_dist (lower = tighter clusters).
    save_html           : If given, save the interactive plot to this path.
    title               : Figure title.
    point_size          : Marker size.
    show                : Whether to call fig.show() immediately.
    random_state        : Seed for reproducibility.

    Returns
    -------
    plotly Figure object (you can further customise it before calling .show()).
    """
    if not HAS_PLOTLY:
        raise ImportError("Install plotly:  pip install plotly")

    # ── 1. Extract fields ─────────────────────────────────────────────────
    field_names, descriptions, block_names, field_ids = _extract_fields(
        md_fields_per_block, md_fields_ids
    )
    n_fields = len(field_names)
    if n_fields == 0:
        raise ValueError("md_fields_per_block contains no fields.")

    print(f"Fields: {n_fields} across {len(md_fields_per_block)} blocks.")

    # ── 2. Embed ──────────────────────────────────────────────────────────
    raw_embs = embed_fn(field_ids, False)
    raw_embs = np.asarray(raw_embs, dtype=np.float32)
    norms = np.linalg.norm(raw_embs, axis=1, keepdims=True)
    embs = raw_embs / np.maximum(norms, 1e-9)

    # ── 3. Reduce to 2D ───────────────────────────────────────────────────
    coords, method_used = _reduce_to_2d(
        embs,
        method=reduction_method,
        umap_n_neighbors=umap_n_neighbors,
        umap_min_dist=umap_min_dist,
        random_state=random_state,
    )
    xs = coords[:, 0]
    ys = coords[:, 1]

    # ── 4. Assign colours per block ───────────────────────────────────────
    unique_blocks = list(dict.fromkeys(block_names))  # preserve insertion order
    n_blocks = len(unique_blocks)
    colors = _palette(n_blocks)
    block_color = {b: colors[i] for i, b in enumerate(unique_blocks)}

    # ── 5. Build one trace per block ──────────────────────────────────────
    traces = []
    for block in unique_blocks:
        mask = [i for i, b in enumerate(block_names) if b == block]
        hover_texts = [
            f"<b>{field_names[i]}</b><br>"
            f"Block: {block_names[i]}<br>"
            f"<i>{descriptions[i][:120]}{'…' if len(descriptions[i]) > 120 else ''}</i>"
            for i in mask
        ]
        trace = go.Scatter(
            x=xs[mask],
            y=ys[mask],
            mode="markers",
            name=block,
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            marker=dict(
                size=point_size,
                color=block_color[block],
                opacity=0.85,
                line=dict(width=0.5, color="white"),
            ),
            customdata=[field_names[i] for i in mask],
        )
        traces.append(trace)

    # ── 6. Compose figure ─────────────────────────────────────────────────
    fig = go.Figure(data=traces)

    fig.update_layout(
        title=dict(text=f"{title} ({method_used})", font=dict(size=15), weight="bold"),
        xaxis_title=f"{method_used} dim 1",
        yaxis_title=f"{method_used} dim 2",
        legend=dict(
            title=dict(text="Block / step", font=dict(size=11)),
            itemsizing="constant",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#CCCCCC",
            borderwidth=1,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="closest",
        width=950,
        height=680,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEEEEE", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#EEEEEE", zeroline=False)

    # ── 7. Annotate field names (optional — can get crowded) ──────────────
    # Uncomment the block below to add text labels on the points.
    # For large schemas (>30 fields) this clutters the plot; use hover instead.
    #
    # for i in range(n_fields):
    #     fig.add_annotation(
    #         x=xs[i], y=ys[i],
    #         text=field_names[i],
    #         showarrow=False,
    #         font=dict(size=7, color="#333333"),
    #         xshift=6, yshift=4,
    #     )

    # ── 8. Save and show ──────────────────────────────────────────────────
    if save_html:
        fig.write_html(save_html)
        print(f"Saved interactive plot → {save_html}")

    if show:
        fig.show()

    return fig


# ── Confidence ellipse helper ─────────────────────────────────────────────────


def _confidence_ellipse(
    xs: np.ndarray,
    ys: np.ndarray,
    confidence: float = 0.90,
    n_points: int = 120,
) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Compute the (x, y) boundary of a confidence ellipse for a 2-D point cloud.

    Uses the eigendecomposition of the covariance matrix.  The ellipse covers
    `confidence` fraction of the data under a Gaussian assumption.

    Returns None when fewer than 3 points are present (ellipse undefined).
    """
    if len(xs) < 3:
        return None

    pts = np.column_stack([xs, ys])
    mu = pts.mean(axis=0)
    cov = np.cov(pts, rowvar=False)

    # χ² quantile for the desired confidence level (2 degrees of freedom)
    scale = np.sqrt(chi2.ppf(confidence, df=2))

    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    # Clip tiny negatives from floating-point noise
    eigenvalues = np.maximum(eigenvalues, 0)

    t = np.linspace(0, 2 * np.pi, n_points)
    # Unit circle scaled by sqrt(eigenvalues) and chi² quantile
    circle = np.column_stack([np.cos(t), np.sin(t)])
    ellipse = scale * circle * np.sqrt(eigenvalues)  # shape (n_points, 2)
    ellipse = ellipse @ eigenvectors.T + mu  # rotate + translate
    return ellipse[:, 0], ellipse[:, 1]


# ── Updated plot_comparison ───────────────────────────────────────────────────


def plot_comparison(
    md_fields_per_block,
    md_fields_ids,
    embed_fn=None,
    reduction_method: str = "auto",
    save_html=None,
    save_png=None,
    png_dpi_scale: int = 4,
    random_state: int = 42,
    # ── ellipse options ───────────────────────────────────────────────────
    drawing_ellipses_names: Optional[List[str]] = None,
    ellipse_confidence: float = 0.90,
    ellipse_alpha: float = 0.13,
    ellipse_line_width: float = 1.6,
    min_points_for_ellipse: int = 3,
    # ── typography ────────────────────────────────────────────────────────
    axis_font_size: int = 20,
    tick_font_size: int = 17,
    subplot_title_font_size: int = 22,
    title_font_size: int = 24,
    legend_font_size: int = 15,
    point_size: int = 11,
):
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    # ── local imports from the enclosing module ───────────────────────────
    from scatter_blocks import (
        _extract_fields,
        _palette,
        _reduce_to_2d,
        _confidence_ellipse,
    )

    FONT_FAMILY = "Times New Roman, Times, serif"
    BLACK = "#000000"

    field_names, descriptions, block_names, field_ids = _extract_fields(
        md_fields_per_block, md_fields_ids
    )
    if not field_names:
        raise ValueError("md_fields_per_block contains no fields.")

    unique_blocks = list(dict.fromkeys(block_names))
    n_blocks = len(unique_blocks)
    colors = _palette(n_blocks)
    block_color = {b: colors[i] for i, b in enumerate(unique_blocks)}

    def _normed(ids, needs_full):
        raw = np.asarray(embed_fn(ids, needs_full), dtype=np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        return raw / np.maximum(norms, 1e-9)

    embs_flat = _normed(field_ids, False)
    embs_aug = _normed(field_ids, True)

    coords_flat, m1 = _reduce_to_2d(
        embs_flat, method=reduction_method, random_state=random_state
    )
    coords_aug, m2 = _reduce_to_2d(
        embs_aug, method=reduction_method, random_state=random_state
    )

    fig_width = fig_height = 900

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            f"Short description embeddings",
            f"DAG-augmented embeddings",
        ),
        shared_yaxes=False,
        horizontal_spacing=0.12,
    )

    # ── data traces + ellipses ────────────────────────────────────────────
    shown_legend: set = set()

    for col_idx, coords in enumerate([coords_flat, coords_aug], start=1):
        xs_all = coords[:, 0]
        ys_all = coords[:, 1]

        for block in unique_blocks:
            mask = [i for i, b in enumerate(block_names) if b == block]
            color = block_color[block]
            show_leg = block not in shown_legend and col_idx == 1
            shown_legend.add(block)

            bxs = xs_all[mask]
            bys = ys_all[mask]

            hover_texts = [
                f"<b>{field_names[i]}</b><br>Block: {block}<br>"
                f"<i>{descriptions[i][:120]}"
                f"{'…' if len(descriptions[i]) > 120 else ''}</i>"
                for i in mask
            ]

            fig.add_trace(
                go.Scatter(
                    x=bxs,
                    y=bys,
                    mode="markers",
                    name=block,
                    legendgroup=block,
                    showlegend=False,  # all data traces hidden
                    text=hover_texts,
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(
                        size=point_size,
                        color=color,
                        opacity=0.88,
                        line=dict(width=0.6, color="white"),
                    ),
                ),
                row=1,
                col=col_idx,
            )

            # ellipses
            should_draw = (
                drawing_ellipses_names is not None
                and block in drawing_ellipses_names
                and len(mask) >= min_points_for_ellipse
            )
            if should_draw:
                result = _confidence_ellipse(bxs, bys, confidence=ellipse_confidence)
                if result is not None:
                    ex, ey = result
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                    fig.add_trace(
                        go.Scatter(
                            x=np.append(ex, ex[0]),
                            y=np.append(ey, ey[0]),
                            mode="lines",
                            fill="toself",
                            fillcolor=f"rgba({r},{g},{b},{ellipse_alpha})",
                            line=dict(
                                color=f"rgba({r},{g},{b},0.70)",
                                width=ellipse_line_width,
                            ),
                            showlegend=False,
                            hoverinfo="skip",
                        ),
                        row=1,
                        col=col_idx,
                    )

    # ── ellipse legend: coloured squares + names, upper-right of col=2 ───
    if drawing_ellipses_names:
        for block in drawing_ellipses_names:
            if block not in block_color:
                continue
            color = block_color[block]
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    name=block,
                    showlegend=True,
                    legendgroup="ellipses",
                    marker=dict(
                        symbol="square",
                        size=12,
                        color=color,
                        opacity=0.75,
                        line=dict(width=1, color=color),
                    ),
                ),
                row=1,
                col=2,  # associate with right panel
            )

    # ── global layout ─────────────────────────────────────────────────────
    fig.update_layout(
        width=fig_width,
        height=fig_height,
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="closest",
        margin=dict(l=70, r=20, t=90, b=60),
        # Legend — upper-right corner of the right subplot
        legend=dict(
            font=dict(size=legend_font_size, family=FONT_FAMILY, color=BLACK, weight="bold"),
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#AAAAAA",
            borderwidth=1,
            x=1.0,
            y=1.0,
            xanchor="right",
            yanchor="top",
        ),
    )

    # Subplot annotation fonts → Times, black, larger
    for ann in fig.layout.annotations:
        ann.font = dict(
            size=subplot_title_font_size, family=FONT_FAMILY, color=BLACK, weight="bold"
        )

    # Axis style
    axis_style = dict(
        showgrid=True,
        gridcolor="#DDDDDD",
        gridwidth=1,
        zeroline=False,
        tickfont=dict(size=tick_font_size, family=FONT_FAMILY, color=BLACK, weight="bold"),
        title_font=dict(size=axis_font_size, family=FONT_FAMILY, color=BLACK, weight="bold"),
        linecolor=BLACK,
        linewidth=1,
    )
    fig.update_xaxes(**axis_style, title_text=f"{m1} dim 1", row=1, col=1)
    fig.update_xaxes(**axis_style, title_text=f"{m2} dim 1", row=1, col=2)
    fig.update_yaxes(**axis_style, title_text=f"{m1} dim 2", row=1, col=1)
    fig.update_yaxes(**axis_style, title_text=f"{m2} dim 2", row=1, col=2)

    # ── save ──────────────────────────────────────────────────────────────
    if save_html:
        fig.write_html(save_html)
        print(f"Saved HTML → {save_html}")

    if save_png:
        try:
            fig.write_image(
                save_png, scale=png_dpi_scale, width=fig_width, height=fig_height
            )
            print(f"Saved PNG → {save_png} (~{96*png_dpi_scale} DPI)")
        except Exception as exc:
            print(f"PNG export failed: {exc}\npip install kaleido")

    if not save_html and not save_png:
        fig.show()

    return fig
