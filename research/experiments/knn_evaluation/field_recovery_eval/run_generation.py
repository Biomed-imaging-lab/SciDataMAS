"""Stage 2: run the m1 and m4 generators over the synthesized blind queries,
across all models in config.MODELS, with config.N_REPEATS independent
generations per (standard, query, model, generator) cell, and save each
raw generated schema.

Both m1 (structured-output parsing) and m4 (DAG/DSL validation) occasionally
fail transiently — a re-invocation with a fresh LLM call typically succeeds.
Each cell is retried up to config.MAX_GENERATION_RETRIES times before the
last error is persisted, so a run always produces a saved result per cell
and transient flakes don't need a full-run restart.

Usage:
    python run_generation.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / "rag_curator" / ".env")

import config
from generators.m1_generator import MDGenerationFlow as M1Flow
from generators.m4_dsl_dag_generator.dag_generator import DAGGenerationFlow
from generators.m4_dsl_dag_generator.md_generator import MDGenerationFlow as M4MDFlow


def read_prompts(path: Path) -> str:
    return path.read_text()


def _is_field_entry(value) -> bool:
    return isinstance(value, dict) and ("descr" in value or "type" in value)


def normalize_m1_output(raw: dict):
    """m1's ChatPromptTemplate | llm.with_structured_output(ModelAnswer,
    method="json_schema", strict=False) is unreliable for some models
    (observed with gpt-5.4-mini: ~2/3 of calls drop the
    {reasoning, generated_metadata_structure} wrapper entirely and return
    the flat md_schema dict as the top-level object instead). Handle both
    shapes here rather than patching the shared M1Flow.
    """
    if not isinstance(raw, dict):
        return None

    gen = raw.get("generated_metadata_structure")
    if isinstance(gen, dict) and isinstance(gen.get("md_schema"), dict) and gen["md_schema"]:
        return {
            "short_name": gen.get("short_name", ""),
            "description": gen.get("description", ""),
            "md_schema": gen["md_schema"],
        }

    # Fallback: model returned the field dict directly at the top level.
    flat_fields = {k: v for k, v in raw.items() if _is_field_entry(v)}
    if flat_fields:
        return {"short_name": "", "description": "", "md_schema": flat_fields}

    return None


def run_m1(query: str, model: str) -> dict:
    flow = M1Flow(read_prompts(config.M1_PROMPT_PATH), model, config.PROVIDER, config.TEMPERATURE)
    raw = flow.chain_with_parsing.invoke({"messages": [("user", query)]})
    gen = normalize_m1_output(raw)
    if gen is None:
        return {"error": "generation_failed: could not normalize structured output"}
    return gen


def run_m4(query: str, model: str) -> dict:
    dag_flow = DAGGenerationFlow(
        read_prompts(config.M4_DAG_PROMPT_PATH), model, config.PROVIDER, config.TEMPERATURE
    )
    dag_state = dag_flow.workflow.invoke(
        {"users_task": query}, config={"recursion_limit": config.M4_RECURSION_LIMIT}
    )
    if dag_state.get("generation_failed") or dag_state.get("dag") is None:
        return {"error": "dag_generation_failed"}

    md_flow = M4MDFlow(
        read_prompts(config.M4_MD_PROMPT_PATH), model, config.PROVIDER, config.TEMPERATURE
    )
    md_state = md_flow.workflow.invoke(
        {
            "users_task": query,
            "md_name": dag_state["raw_dag"].md_name,
            "md_description": dag_state["raw_dag"].md_descr,
            "dag": dag_state["dag"],
        },
        config={"recursion_limit": config.M4_RECURSION_LIMIT},
    )
    if md_state.get("md_gen_failed") or not md_state.get("fields_per_node"):
        return {"error": "md_generation_failed"}

    fields_per_node = {
        node_id: {
            "reasoning": gen.reasoning,
            "md_schema": [f.model_dump() for f in gen.md_schema],
        }
        for node_id, gen in md_state["fields_per_node"].items()
    }
    return {
        "md_name": dag_state["raw_dag"].md_name,
        "md_description": dag_state["raw_dag"].md_descr,
        "fields_per_node": fields_per_node,
    }


GENERATOR_RUNNERS = {"m1": run_m1, "m4": run_m4}


def generate_with_retries(gen_name: str, query: str, model: str) -> dict:
    last_result = {"error": "no_attempts_made"}
    for attempt in range(1, config.MAX_GENERATION_RETRIES + 1):
        try:
            last_result = GENERATOR_RUNNERS[gen_name](query, model)
        except Exception as exc:
            last_result = {"error": f"exception: {exc}"}

        if "error" not in last_result:
            return last_result

        print(f"    retry {attempt}/{config.MAX_GENERATION_RETRIES} after: {last_result['error']}")
        if attempt < config.MAX_GENERATION_RETRIES:
            time.sleep(config.GENERATION_RETRY_BACKOFF_SECONDS)

    last_result["attempts"] = config.MAX_GENERATION_RETRIES
    return last_result


def cell_needs_generation(out_path: Path) -> bool:
    if not out_path.exists():
        return True
    try:
        saved = json.loads(out_path.read_text())
    except (json.JSONDecodeError, OSError):
        return True
    return "error" in saved


def main():
    query_paths = sorted(config.QUERIES_DIR.glob("*.json"))
    print(f"Found {len(query_paths)} query banks.")

    for qpath in query_paths:
        standard_key = qpath.stem
        queries = json.loads(qpath.read_text())

        for query_idx, q in enumerate(queries):
            for repeat_idx in range(config.N_REPEATS):
                for model in config.MODELS:
                    for gen_name in config.GENERATORS:
                        out_dir = (
                            config.GENERATIONS_DIR
                            / standard_key
                            / str(query_idx)
                            / str(repeat_idx)
                            / model
                        )
                        out_path = out_dir / f"{gen_name}.json"
                        if not cell_needs_generation(out_path):
                            continue

                        out_dir.mkdir(parents=True, exist_ok=True)
                        print(
                            f"[generate] {standard_key} q{query_idx} r{repeat_idx} {model} {gen_name}"
                        )
                        result = generate_with_retries(gen_name, q["llm_query"], model)

                        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
