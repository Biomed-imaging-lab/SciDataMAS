"""Stage 3: for each generated cell, embed ground-truth vs. generated fields,
run the FieldsComparator LLM-judge escalation (the class is reused as-is from
eval/judges/repeating/fields_repeating.py, but loaded with this experiment's
own coverage-judge prompt — see prompts/recall_judge.txt — since the shared
fields_comparer.txt prompt checks strict field equivalence, whereas recall
here needs a directional "does the generated field capture this GT field's
info, fully or in part" judgment), and compute directional recall: the
fraction of the *approved standard's* fields that are covered by some
generated field.

Only evaluates models listed in config.MODELS (guards against stale
generation output left on disk from a different model).

Rows are appended to RESULTS_CSV incrementally (one per cell) and already-
evaluated (standard, query, repeat, model, generator) cells are skipped on
rerun, so a transient failure (e.g. an embeddings API connection error)
loses only the in-flight cell, not the whole run — just rerun this script.

Usage:
    python run_recall_eval.py
"""

import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / "rag_curator" / ".env")

import numpy as np
from langchain_openai import OpenAIEmbeddings

import config
from md_conversion import flatten_m4, load_approved_standard, m1_output_to_mdfields
from eval.judges.repeating.fields_repeating import CompareState, FieldsComparator
from eval.md_classes import MDField
from eval.variarity import semantic_compare

FIELDNAMES = [
    "standard_id",
    "query_idx",
    "repeat_idx",
    "model",
    "generator",
    "n_gt_fields",
    "n_matched",
    "recall",
    "status",
]


def read_prompts(path: Path) -> str:
    return path.read_text()


def embed_fields(
    fields: Dict[str, MDField], embedder: OpenAIEmbeddings, max_retries: int = 3
) -> Dict[str, np.ndarray]:
    result = {}
    for name, field in fields.items():
        for attempt in range(1, max_retries + 1):
            try:
                result[name] = np.array(embedder.embed_query(str(field)))
                break
            except Exception as exc:
                if attempt == max_retries:
                    raise
                print(f"    embedding retry {attempt}/{max_retries} after: {exc}")
                time.sleep(2 * attempt)
    return result


def make_judge(field_comparer: FieldsComparator, md_name: str, md_descr: str, max_retries: int = 3):
    def llm_judge(target_field: str, candidates: List[str]) -> List[str]:
        state = CompareState()
        state["md_schema_name"] = md_name
        state["md_schema_descr"] = md_descr
        state["main_field_str"] = target_field
        state["potention_similar_fields"] = candidates
        for attempt in range(1, max_retries + 1):
            try:
                res = field_comparer.workflow.invoke(state)
                return res["result"].same_fields_from_list
            except Exception as exc:
                if attempt == max_retries:
                    raise
                print(f"    judge retry {attempt}/{max_retries} after: {exc}")
                time.sleep(2 * attempt)

    return llm_judge


def recall_from_pairs(gt_pairs: Dict[str, set]) -> int:
    return sum(1 for matches in gt_pairs.values() if len(matches) > 0)


def load_generated_fields(gen_path: Path) -> Dict[str, MDField]:
    data = json.loads(gen_path.read_text())
    if "error" in data:
        return None
    gen_name = gen_path.stem
    if gen_name == "m1":
        return m1_output_to_mdfields(data["md_schema"])
    if gen_name == "m4":
        return flatten_m4(data["fields_per_node"])
    raise ValueError(f"Unknown generator output: {gen_path}")


def load_done_cells(path: Path) -> Set[Tuple[str, str, str, str, str]]:
    """Cells with a persisted status are skipped on rerun, except
    eval_failed (a retriable transient failure, unlike generation_failed
    which reflects a permanently-missing generation)."""
    if not path.exists():
        return set()
    done = set()
    with open(path, newline="") as fio:
        for row in csv.DictReader(fio):
            if row["status"].startswith("eval_failed"):
                continue
            done.add(
                (
                    row["standard_id"],
                    row["query_idx"],
                    row["repeat_idx"],
                    row["model"],
                    row["generator"],
                )
            )
    return done


def append_row(path: Path, row: dict, write_header: bool):
    with open(path, "a", newline="") as fio:
        writer = csv.DictWriter(fio, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main():
    embedder = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    field_comparer = FieldsComparator(
        read_prompts(config.RECALL_JUDGE_PROMPT_PATH),
        config.JUDGE_MODEL,
        config.JUDGE_PROVIDER,
        config.JUDGE_TEMPERATURE,
    )

    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    done_cells = load_done_cells(config.RESULTS_CSV)
    write_header = not config.RESULTS_CSV.exists()
    n_written = 0

    standard_filter = set(sys.argv[1:]) or None  # optional: restrict to these standard_key stems
    standard_paths = sorted(config.APPROVED_TABLES_DIR.glob("*.json"))
    if standard_filter:
        standard_paths = [p for p in standard_paths if p.stem in standard_filter]
        print(f"Restricting to {len(standard_paths)} standard(s): {sorted(standard_filter)}")
    for spath in standard_paths:
        info = load_approved_standard(spath)
        standard_key = info["standard_key"]
        gt_fields = info["gt_fields"]
        if not gt_fields:
            continue

        gen_root = config.GENERATIONS_DIR / standard_key
        if not gen_root.exists():
            continue

        # only embed ground truth once we know there's at least one cell left to do
        pending_query_dirs = sorted(gen_root.iterdir(), key=lambda p: int(p.name))
        if not pending_query_dirs:
            continue

        gt_embeds = None  # lazily computed on first needed cell for this standard

        for query_dir in pending_query_dirs:
            query_idx = query_dir.name
            for repeat_dir in sorted(query_dir.iterdir(), key=lambda p: int(p.name)):
                repeat_idx = repeat_dir.name
                for model_dir in sorted(repeat_dir.iterdir()):
                    model = model_dir.name
                    if model not in config.MODELS:
                        continue
                    for gen_path in sorted(model_dir.glob("*.json")):
                        gen_name = gen_path.stem
                        cell_key = (standard_key, query_idx, repeat_idx, model, gen_name)
                        if cell_key in done_cells:
                            continue

                        print(
                            f"[eval] {standard_key} q{query_idx} r{repeat_idx} {model} {gen_name}"
                        )

                        gen_fields = load_generated_fields(gen_path)
                        if not gen_fields:
                            row = {
                                "standard_id": standard_key,
                                "query_idx": query_idx,
                                "repeat_idx": repeat_idx,
                                "model": model,
                                "generator": gen_name,
                                "n_gt_fields": len(gt_fields),
                                "n_matched": "",
                                "recall": "",
                                "status": "generation_failed",
                            }
                            append_row(config.RESULTS_CSV, row, write_header)
                            write_header = False
                            done_cells.add(cell_key)
                            n_written += 1
                            continue

                        try:
                            if gt_embeds is None:
                                gt_embeds = embed_fields(gt_fields, embedder)

                            gen_embeds = embed_fields(gen_fields, embedder)
                            judge = make_judge(field_comparer, standard_key, info["abstract"])

                            pairs_gt, _ = semantic_compare(
                                gt_fields,
                                gen_fields,
                                gt_embeds,
                                gen_embeds,
                                judge,
                                are_equal_thres=config.ARE_EQUAL_THRES,
                                need_comp_thres=config.NEED_COMP_THRES,
                                stable_runs=config.STABLE_RUNS,
                            )
                            n_matched = recall_from_pairs(pairs_gt)
                            n_gt = len(gt_fields)
                            row = {
                                "standard_id": standard_key,
                                "query_idx": query_idx,
                                "repeat_idx": repeat_idx,
                                "model": model,
                                "generator": gen_name,
                                "n_gt_fields": n_gt,
                                "n_matched": n_matched,
                                "recall": n_matched / n_gt if n_gt else "",
                                "status": "ok",
                            }
                        except Exception as exc:
                            print(f"    [FAILED after retries] {exc}")
                            row = {
                                "standard_id": standard_key,
                                "query_idx": query_idx,
                                "repeat_idx": repeat_idx,
                                "model": model,
                                "generator": gen_name,
                                "n_gt_fields": len(gt_fields),
                                "n_matched": "",
                                "recall": "",
                                "status": f"eval_failed: {exc}",
                            }

                        append_row(config.RESULTS_CSV, row, write_header)
                        write_header = False
                        done_cells.add(cell_key)
                        n_written += 1

    print(f"Wrote {n_written} new rows to {config.RESULTS_CSV} (total {len(done_cells)} cells done)")


if __name__ == "__main__":
    main()
