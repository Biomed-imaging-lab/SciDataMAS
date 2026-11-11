from .md_classes import MDField

from typing import Dict, Callable, List, Dict, Tuple

import numpy as np


def semantic_compare(
    fields1: Dict[str, MDField],
    fields2: Dict[str, MDField],
    emb_fields1: Dict[str, np.ndarray],
    emb_fields2: Dict[str, np.ndarray],
    semantic_judge: Callable[[str, List[str]], List[str]],
    are_equal_thres: float = 0.95,
    need_comp_thres: float = 0.5,
    stable_runs: int = 1,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Algorithm for compairing two fields list by thier semantic
    Returns the two sets of equal fields: for each field from first - the equivalent from
    """

    if not fields1 or not fields2:
        return {}, {}

    names1 = list(fields1.keys())
    first_embeds = [emb_fields1[f] for f in fields1.keys()]
    first_embeds = np.array(first_embeds, dtype=np.float32)
    norms = np.linalg.norm(first_embeds, axis=1, keepdims=True)
    first_embeds = first_embeds / np.maximum(norms, 1e-9)

    names2 = list(fields2.keys())
    second_embeds = [emb_fields2[f] for f in fields2.keys()]
    second_embeds = np.array(second_embeds, dtype=np.float32)
    norms = np.linalg.norm(second_embeds, axis=1, keepdims=True)
    second_embeds = second_embeds / np.maximum(norms, 1e-9)

    similarity = first_embeds @ second_embeds.T

    pairs_first = {fn1: set() for fn1 in names1}
    pairs_second = {fn2: set() for fn2 in names2}

    # build canditates indexes
    candidates_first = {fn1: [] for fn1 in names1}
    candidates_second = {fn2: [] for fn2 in names2}
    for i in range(len(names1)):
        for j in range(len(names2)):
            s = float(similarity[i, j])
            if s >= need_comp_thres:
                candidates_first[names1[i]].append((j, s))
                candidates_second[names2[j]].append((i, s))

    # sort and add candidates for 1st field
    for fn1 in names1:
        needs_judgement = []
        for elem in candidates_first[fn1]:
            idx, sim = elem[0], elem[1]
            if sim >= are_equal_thres:
                pairs_first[fn1].add(names2[idx])
                pairs_second[names2[idx]].add(fn1)
            else:
                full_str = fields2[names2[idx]]
                needs_judgement.append(str(full_str))

        if needs_judgement:
            # TODO: make frequency like counting (like 2 from 3)
            # make some runs for stability
            results = [
                semantic_judge(str(fields1[fn1]), needs_judgement)
                for _ in range(stable_runs)
            ]
            sets = [set(r) for r in results]
            stable_set = sets[0]

            for i in range(1, len(sets)):
                stable_set = stable_set & sets[i]

            confirmed_strs_names = stable_set.intersection(set(names2))
            pairs_first[fn1].update(confirmed_strs_names)

            for entry in confirmed_strs_names:
                pairs_second[entry].update({fn1})

    return pairs_first, pairs_second


def count_fields_variance(
    fields1: Dict[str, MDField],
    fields2: Dict[str, MDField],
    emb_fields1: Dict[str, np.ndarray],
    emb_fields2: Dict[str, np.ndarray],
    semantic_judge: Callable[[str, List[str]], List[str]],
    are_equal_thres: float = 0.95,
    need_comp_thres: float = 0.5,
    stable_runs: int = 1,
):

    sc_1, sc_2 = semantic_compare(
        fields1,
        fields2,
        emb_fields1,
        emb_fields2,
        semantic_judge,
        are_equal_thres,
        need_comp_thres,
        stable_runs,
    )

    unique_1 = 0
    unique_2 = 0

    for _, v in sc_1.items():
        if len(v) == 0:
            unique_1 += 1

    for _, v in sc_2.items():
        if len(v) == 0:
            unique_2 += 1

    size_1 = len(fields1.keys())
    size_2 = len(fields1.keys())

    matched_1 = size_1 - unique_1
    matched_2 = size_2 - unique_2
    intersection = (matched_1 + matched_2) / 2
    union = size_1 + size_2 - intersection

    # Warning! Do not confuse with IoU - for IoU we need like detecting subset S as intersection of F1 and F2.
    # Here we estimate the similar fields based on finding the S2 as a some projection of F1 elements (the elements of F1, which have some
    # semanticly near fields in F2, are making S1 set)

    # but we always can estimate the IoU
    return {
        "variance": (unique_1 + unique_2) / (size_1 + size_2),
        "iou": intersection / union if union > 0 else 1.0,
    }
