from .md_classes import MDField

from typing import Dict, Callable, List, Dict, Tuple, Optional

import numpy as np


def self_semantic_compare(
    fields: Dict[str, MDField],
    emb_fields: Dict[str, np.ndarray],
    semantic_judge: Callable[[str, List[str]], List[str]],
    are_equal_thres: float = 0.95,
    need_comp_thres: float = 0.5,
    stable_runs: int = 1,
    max_similars: Optional[int] = None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Algorithm for compairing two fields list by thier semantic
    Returns the two sets of equal fields: for each field from first - the equivalent from
    """

    if not fields:
        return {}, {}

    names = list(fields.keys())

    embeds = [emb_fields[f] for f in fields.keys()]
    embeds = np.array(embeds, dtype=np.float32)
    norms = np.linalg.norm(embeds, axis=1, keepdims=True)
    embeds = embeds / np.maximum(norms, 1e-9)

    similarity = embeds @ embeds.T

    # build canditates indexes
    pairs = {fn: set() for fn in names}
    candidates = {fn: [] for fn in names}

    for i in range(0, len(names) - 1):
        for j in range(i + 1, len(names)):
            s = float(similarity[i, j])
            if s >= need_comp_thres:
                candidates[names[i]].append((j, s))
                candidates[names[j]].append((i, s))

    # sort and add candidates for 1st field
    for fn in names:
        # sort candidates and cut the lowest rest
        if max_similars != None and max_similars > 0:
            lim = len(candidates[fn])
            candidates[fn].sort(key=lambda x: -x[1])
            lim = min(lim, max_similars)
            candidates[fn] = candidates[fn][0:lim]

        needs_judgement = []
        for elem in candidates[fn]:
            idx, sim = elem[0], elem[1]
            if sim >= are_equal_thres:
                pairs[fn].add(names[idx])
                pairs[names[idx]].add(fn)
            else:
                full_str = fields[names[idx]]
                needs_judgement.append(str(full_str))

        if needs_judgement:
            results = [
                semantic_judge(str(fields[fn]), needs_judgement)
                for _ in range(stable_runs)
            ]
            sets = [set(r) for r in results]
            stable_set = sets[0]
            for i in range(1, len(sets)):
                stable_set = stable_set & sets[i]

            confirmed_strs_names = stable_set.intersection(set(names))
            confirmed_strs_names.discard(fn)
            pairs[fn].update(confirmed_strs_names)

    # leave only symmetric matches (for additional of llm-as-a-judge robustness)
    final_match = {fn: set() for fn in names}

    for fk, fv in pairs.items():
        for matched in fv:
            if fk in pairs[matched]:
                final_match[fk].add(matched)
                final_match[matched].add(fk)

    return final_match


def count_self_repeating_part(
    fields: Dict[str, MDField],
    emb_fields: Dict[str, np.ndarray],
    semantic_judge: Callable[[str, List[str]], List[str]],
    are_equal_thres: float = 0.95,
    need_comp_thres: float = 0.5,
    stable_runs: int = 1,
    max_similars: Optional[int] = None,
):

    sc = self_semantic_compare(
        fields,
        emb_fields,
        semantic_judge,
        are_equal_thres,
        need_comp_thres,
        stable_runs,
        max_similars,
    )

    unique = 0
    for _, v in sc.items():
        if len(v) == 0:
            unique += 1

    size = len(fields.keys())

    # This is the exactly count of self-citing in fields
    return 1 - unique / size
