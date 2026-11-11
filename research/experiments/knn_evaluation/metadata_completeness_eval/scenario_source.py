"""Scenario sourcing: where probe grounding text and Expert-side metadata
come from. Two modes share the same downstream engine (Retriever + Probe);
only this module differs between them.
"""

import json
import re
import sys
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import pandas as pd

import config as mce_config

sys.path.insert(0, str(mce_config.FIELD_RECOVERY_ROOT))
sys.path.insert(0, str(mce_config.KNN_EVAL_ROOT))

from eval.md_classes import DataStep, MDField  # noqa: E402
from md_conversion import load_approved_standard  # noqa: E402


class ScenarioProvider(ABC):
    @abstractmethod
    def get_metadata(self, target_key: str) -> Dict[str, MDField]: ...

    @abstractmethod
    def get_scenarios(self, target_key: str, k: int) -> List[str]:
        """Blind grounding text for the probe's task_scenario — must never
        contain field names or anything else drawn from get_metadata()."""
        ...


class ApprovedTableScenarioProvider(ScenarioProvider):
    """Phase 1: real curated standards from rag_curator/tmp_res/approved_tables.

    Metadata = the standard's own field list (load_approved_standard, reused
    unmodified from field_recovery_eval). Scenarios = the blind experiment
    descriptions field_recovery_eval already synthesized per standard
    (outputs/queries/{target_key}.json) — reused as-is rather than
    resynthesized, since they are already blind by construction (see
    field_recovery_eval/prompts/query_synthesis.txt).
    """

    def get_metadata(self, target_key: str) -> Dict[str, MDField]:
        path = mce_config.APPROVED_TABLES_DIR / f"{target_key}.json"
        info = load_approved_standard(path)
        return info["gt_fields"]

    def get_scenarios(self, target_key: str, k: int) -> List[str]:
        path = mce_config.QUERIES_DIR / f"{target_key}.json"
        data = json.loads(path.read_text())
        queries = [entry["llm_query"] for entry in data]
        if not queries:
            raise ValueError(f"No synthesized queries found for {target_key} at {path}")
        return [queries[i % len(queries)] for i in range(k)]


_TARGET_KEY_RE = re.compile(r"^(m1|m4)_q(\d+)$")


@lru_cache(maxsize=2)
def _load_csv(algo: str) -> pd.DataFrame:
    path = mce_config.GENERATION_DATA_DIR / f"{algo}_synth_bio_mds.csv"
    return pd.read_csv(path)


def parse_generation_target_key(target_key: str):
    m = _TARGET_KEY_RE.match(target_key)
    if not m:
        raise ValueError(f"Not a generation target key (expected 'm1_qN' or 'm4_qN'): {target_key}")
    return m.group(1), int(m.group(2))


class GenerationScenarioProvider(ScenarioProvider):
    """Phase 2: score our own m1/m4 generations (already-run, denormalized
    CSVs in experiments/knn_evaluation/data/), grounded in the original
    bio_queries.yaml scenario each generation was produced from — reused
    directly from the CSV's own `query_llm_query` column rather than
    re-reading bio_queries.yaml separately, since the two are already
    matched 1:1 by query_id.

    target_key format: "{m1|m4}_q{query_id}", e.g. "m1_q0", "m4_q15".
    Only run_id == 0 is used (one generation per query per algorithm, per
    the scoped Phase 2 plan: 16 queries x 2 algorithms x 1 run = 32 targets).
    """

    def get_metadata(self, target_key: str) -> Dict[str, MDField]:
        algo, query_id = parse_generation_target_key(target_key)
        df = _load_csv(algo)
        rows = df[(df.query_id == query_id) & (df.run_id == 0)]
        if rows.empty:
            raise ValueError(f"No rows for {target_key} (algo={algo}, query_id={query_id}, run_id=0)")

        fields: Dict[str, MDField] = {}
        for _, row in rows.iterrows():
            block = None
            if algo == "m4" and pd.notna(row.get("node_name")):
                block = DataStep(name=row["node_name"], descr=row.get("node_descr", "") or "")
            fields[row["field_name"]] = MDField(
                name=row["field_name"],
                descr=row.get("field_description", "") or "",
                type=row.get("field_type", "") or "",
                block=block,
            )
        return fields

    def get_scenarios(self, target_key: str, k: int) -> List[str]:
        algo, query_id = parse_generation_target_key(target_key)
        df = _load_csv(algo)
        rows = df[(df.query_id == query_id) & (df.run_id == 0)]
        if rows.empty:
            raise ValueError(f"No rows for {target_key} (algo={algo}, query_id={query_id}, run_id=0)")
        query_text = rows.iloc[0]["query_llm_query"]
        return [query_text] * k


def get_provider_for(target_key: str) -> ScenarioProvider:
    """Dispatch by target_key shape — the two namespaces never collide
    (approved-table keys look like '523_REMBI__REMBI', generation keys look
    like 'm1_q3'/'m4_q3')."""
    if _TARGET_KEY_RE.match(target_key):
        return GenerationScenarioProvider()
    return ApprovedTableScenarioProvider()
