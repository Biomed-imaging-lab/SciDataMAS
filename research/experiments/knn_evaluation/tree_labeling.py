from typing import Dict, List, Optional
from sklearn.cluster import AgglomerativeClustering


# ── LLM mockup ───────────────────────────────────────────────────────────────

def union_clusters_with_llm(
    cluster_name1: str,
    cluster_descr1: str,
    cluster_name2: str,
    cluster_descr2: str,
    cluster_contain1: Optional[List[str]] = None,
    cluster_contain2: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    Replace this with your real LLM call.

    The function must return a dict with exactly two keys:
        {"name": <str>, "description": <str>}

    Arguments
    ---------
    cluster_name1     : Short name of the left child cluster.
    cluster_descr1    : Description of the left child cluster.
    cluster_name2     : Short name of the right child cluster.
    cluster_descr2    : Description of the right child cluster.
    cluster_contain1  : Leaf field names contained in the left child (optional).
    cluster_contain2  : Leaf field names contained in the right child (optional).
    """

    state = ClusterDescState()
    state['first_cluster_name'] = cluster_name1
    state['second_cluster_name'] = cluster_name2
    
    state['first_cluster_descr'] = cluster_descr1
    state['second_cluster_descr']= cluster_descr2
    
    state['clusters_fields_1'] = cluster_contain1
    state['clusters_fields_2'] = cluster_contain2

    wf = cluster_unioner.workflow
    response_state = wf.invoke(state)
    merged_name = response_state['union_result'].cluster_description.short_name
    merged_descr = response_state['union_result'].cluster_description.description
    
    return {"name": merged_name, "description": merged_descr}


# ── Core traversal ────────────────────────────────────────────────────────────

def build_cluster_descriptions(
    model: AgglomerativeClustering,
    field_names: List[str],
    field_descriptions: List[str],
    include_contains: bool = True,
    verbose: bool = True,
) -> Dict[int, Dict]:
    """
    Walk the agglomerative tree bottom-up and build a name + description
    for every node (leaf and internal).

    Parameters
    ----------
    model             : Fitted AgglomerativeClustering (distance_threshold=0,
                        n_clusters=None so the full tree is stored).
    field_names       : List of field name strings, length = n_samples.
                        Index i corresponds to leaf node i.
    field_descriptions: List of field description strings, same length.
    system_prompt     : System prompt passed to every LLM call.
    llm_call          : Callable with the signature of llm_call_mockup above.
    include_contains  : If True, pass cluster_contain1/2 to the LLM call.
    verbose           : Print progress.

    Returns
    -------
    node_info : Dict[int, Dict] with one entry per node.
        Keys  : node index (0 … 2*n_samples - 2).
        Values: {
            "name":        str,
            "description": str,
            "contains":    List[str],   # all leaf field names under this node
            "is_leaf":     bool,
            "left":        Optional[int],   # left child index (None for leaves)
            "right":       Optional[int],   # right child index
        }
    """
    n_samples = len(field_names)
    n_merges  = model.children_.shape[0]

    if len(field_names) != n_samples or len(field_descriptions) != n_samples:
        raise ValueError(
            "field_names and field_descriptions must have the same length "
            "as the number of samples the model was fitted on."
        )

    node_info: Dict[int, Dict] = {}

    # ── Step 1: initialise leaf nodes ─────────────────────────────────────
    for i in range(n_samples):
        node_info[i] = {
            "name":        field_names[i],
            "description": field_descriptions[i],
            "contains":    [field_names[i]],
            "is_leaf":     True,
            "left":        None,
            "right":       None,
        }

    # ── Step 2: iterate over merges in order (bottom-up by construction) ──
    # children_[k] = (left, right) are the two children merged at step k.
    # The new internal node gets index n_samples + k.
    for k, (left, right) in enumerate(model.children_):
        internal_idx = n_samples + k
        left_info  = node_info[left]
        right_info = node_info[right]

        if verbose:
            print(
                f"  merge {k+1}/{n_merges}: "
                f"node {left} ({left_info['name']!r}) +"
                f" node {right} ({right_info['name']!r})"
                f" → node {internal_idx}"
            )

        # Build contains list (union of both children)
        combined_contains = left_info["contains"] + right_info["contains"]

        # ── LLM call ──────────────────────────────────────────────────────
        llm_kwargs = dict(
            cluster_name1    = left_info["name"],
            cluster_descr1   = left_info["description"],
            cluster_name2    = right_info["name"],
            cluster_descr2   = right_info["description"],
        )
        if include_contains:
            llm_kwargs["cluster_contain1"] = left_info["contains"]
            llm_kwargs["cluster_contain2"] = right_info["contains"]

        result = union_clusters_with_llm(**llm_kwargs)

        node_info[internal_idx] = {
            "name":        result["name"],
            "description": result["description"],
            "contains":    combined_contains,
            "is_leaf":     False,
            "left":        int(left),
            "right":       int(right),
        }

    return node_info


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_root(node_info: Dict[int, Dict]) -> int:
    """Return the index of the root node (the last merge)."""
    return max(node_info.keys())


def print_tree(
    node_info: Dict[int, Dict],
    node: Optional[int] = None,
    depth: int = 0,
    max_depth: Optional[int] = None,
) -> None:
    """
    Pretty-print the labeled tree for inspection.

    Parameters
    ----------
    node_info : Output of build_cluster_descriptions.
    node      : Node index to start from. Defaults to root.
    depth     : Current indentation depth (used in recursion).
    max_depth : Stop printing below this depth. None = print everything.
    """
    if node is None:
        node = get_root(node_info)

    if max_depth is not None and depth > max_depth:
        return

    info = node_info[node]
    indent = "  " * depth
    leaf_marker = " [leaf]" if info["is_leaf"] else ""
    n_fields = len(info["contains"])

    print(f"{indent}[{node}]{leaf_marker} {info['name']!r}  ({n_fields} fields)")
    print(f"{indent}  → {info['description'][:80]}{'…' if len(info['description']) > 80 else ''}")

    if not info["is_leaf"]:
        print_tree(node_info, info["left"],  depth + 1, max_depth)
        print_tree(node_info, info["right"], depth + 1, max_depth)


def flat_cut(
    node_info: Dict[int, Dict],
    model: AgglomerativeClustering,
    n_clusters: int,
) -> Dict[int, Dict]:
    """
    Return only the internal nodes that correspond to a flat cut of the tree
    into n_clusters clusters — i.e. the nodes that sklearn would return if
    you had set n_clusters=n_clusters.

    Useful for getting a human-readable summary at a chosen granularity
    without re-fitting the model.

    Returns
    -------
    Dict mapping cluster_id (0 … n_clusters-1) to node_info entry,
    with an extra key "cluster_id" added.
    """
    n_samples = len(model.labels_)
    n_merges  = model.children_.shape[0]

    # Replay sklearn's own cut: the last (n_clusters - 1) merges are undone.
    # Active nodes start as all leaves, then we apply merges stopping early.
    active: set[int] = set(range(n_samples))
    n_merges_to_apply = n_samples - n_clusters

    for k in range(n_merges_to_apply):
        left, right = int(model.children_[k, 0]), int(model.children_[k, 1])
        internal = n_samples + k
        active.discard(left)
        active.discard(right)
        active.add(internal)

    result = {}
    for cid, node_idx in enumerate(sorted(active)):
        entry = dict(node_info[node_idx])
        entry["cluster_id"] = cid
        result[cid] = entry

    return result