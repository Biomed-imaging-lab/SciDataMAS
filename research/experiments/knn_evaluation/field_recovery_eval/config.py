from pathlib import Path

FIELD_RECOVERY_ROOT = Path(__file__).resolve().parent
KNN_EVAL_ROOT = FIELD_RECOVERY_ROOT.parent
REPO_ROOT = KNN_EVAL_ROOT.parent.parent

APPROVED_TABLES_DIR = REPO_ROOT / "rag_curator" / "tmp_res" / "approved_tables"

OUTPUTS_DIR = FIELD_RECOVERY_ROOT / "outputs"
QUERIES_DIR = OUTPUTS_DIR / "queries"
GENERATIONS_DIR = OUTPUTS_DIR / "generations"
RESULTS_CSV = OUTPUTS_DIR / "results.csv"
SUMMARY_CSV = OUTPUTS_DIR / "summary.csv"

# --- generation matrix ---
K_QUERIES = 3
N_REPEATS = 3  # metadata generations per query, per model, per generator
MODELS = ["gpt-5.4-mini"]
GENERATORS = ["m1", "m4"]
PROVIDER = "openai"
TEMPERATURE = 0.0
MAX_GENERATION_RETRIES = 3  # per-cell retries on structured-output/DAG-validation failures
GENERATION_RETRY_BACKOFF_SECONDS = 2

# --- query synthesizer ---
SYNTH_MODEL = "gpt-4o"
SYNTH_PROVIDER = "openai"
SYNTH_TEMPERATURE = 0.7

# --- recall judge ---
JUDGE_MODEL = "gpt-5.4-mini"
JUDGE_PROVIDER = "openai"
JUDGE_TEMPERATURE = 0.0
EMBEDDING_MODEL = "text-embedding-3-large"
ARE_EQUAL_THRES = 0.95
NEED_COMP_THRES = 0.45
STABLE_RUNS = 1

# --- prompt paths ---
M1_PROMPT_PATH = KNN_EVAL_ROOT / "prompts" / "md_generation" / "m1_baseline_prompt.txt"
M4_DAG_PROMPT_PATH = (
    KNN_EVAL_ROOT / "prompts" / "md_generation" / "m4_dsl_dag_gen" / "dag_generation.txt"
)
M4_MD_PROMPT_PATH = (
    KNN_EVAL_ROOT / "prompts" / "md_generation" / "m4_dsl_dag_gen" / "md_generation.txt"
)
FIELDS_COMPARER_PROMPT_PATH = KNN_EVAL_ROOT / "prompts" / "llm_judges" / "fields_comparer.txt"
RECALL_JUDGE_PROMPT_PATH = FIELD_RECOVERY_ROOT / "prompts" / "recall_judge.txt"
QUERY_SYNTHESIS_PROMPT_PATH = FIELD_RECOVERY_ROOT / "prompts" / "query_synthesis.txt"

M4_RECURSION_LIMIT = 300
