from pathlib import Path

MCE_ROOT = Path(__file__).resolve().parent
KNN_EVAL_ROOT = MCE_ROOT.parent
REPO_ROOT = KNN_EVAL_ROOT.parent.parent

FIELD_RECOVERY_ROOT = KNN_EVAL_ROOT / "field_recovery_eval"
APPROVED_TABLES_DIR = REPO_ROOT / "rag_curator" / "tmp_res" / "approved_tables"
QUERIES_DIR = FIELD_RECOVERY_ROOT / "outputs" / "queries"  # reused, not regenerated here
GENERATION_DATA_DIR = KNN_EVAL_ROOT / "data"  # m1_synth_bio_mds.csv, m4_synth_bio_mds.csv

OUTPUTS_DIR = MCE_ROOT / "outputs"
RECORDS_DIR = OUTPUTS_DIR / "records"
SUMMARY_DIR = OUTPUTS_DIR / "summary"

# --- probing matrix ---
K_RUNS = 3
# Each (run, probe) is one open-ended session, not a fixed question count:
# the probe keeps asking until it decides it has what it needs for its task,
# bounded by [MIN_QUESTIONS, MAX_QUESTIONS] enforced in code (below MIN the
# probe isn't offered a "stop" option at all; at MAX the loop ends without
# calling the LLM again).
MIN_QUESTIONS = 3
MAX_QUESTIONS = 20

# --- probe model ---
PROBE_MODEL = "gpt-4o"
PROBE_PROVIDER = "openai"
ASK_TEMPERATURE = 0.7
JUDGE_TEMPERATURE = 0.0

# --- retriever ---
EMBEDDING_MODEL = "text-embedding-3-large"
# Calibrated empirically for question->field cosine similarity on REMBI (see
# plan/dry-run notes): true-match top scores land ~0.37-0.55, while a
# deliberately unrelated question tops out ~0.20. field_recovery_eval's
# 0.45 is calibrated for field<->field similarity (a different, higher-
# baseline regime) and is NOT reusable here.
NEED_COMP_THRES = 0.28
MAX_CANDIDATES = 5

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# --- prompt paths ---
# probe_ask.txt is the session-level system prompt (role/task/scenario framing,
# built once per session); the _turn files are the small per-iteration user
# instructions appended to the running transcript each time.
PROBE_SESSION_PROMPT_PATH = MCE_ROOT / "prompts" / "probe_ask.txt"
PROBE_ASK_TURN_PROMPT_PATH = MCE_ROOT / "prompts" / "probe_ask_turn.txt"
PROBE_JUDGE_TURN_PROMPT_PATH = MCE_ROOT / "prompts" / "probe_judge_turn.txt"

# --- cache ---
CACHE_DIR = MCE_ROOT / "cache"

# --- Phase 1 default targets ---
# All curated standards with an approved_tables JSON — kept dynamic (rather
# than a hardcoded list) so a new standard dropped into that directory is
# picked up automatically, as long as it also has synthesized queries.
ALL_APPROVED_TABLE_TARGETS = sorted(p.stem for p in APPROVED_TABLES_DIR.glob("*.json"))
DEFAULT_TARGETS = ALL_APPROVED_TABLE_TARGETS

# --- Phase 2: our own m1/m4 generations ---
# Scoped per the user's directive: 1 run per (algorithm, query) rather than
# K_RUNS repeats, since bio_queries.yaml already provides diversity across
# 16 distinct queries x 2 algorithms = 32 targets. Each target still gets a
# full open-ended probing session per probe (K_RUNS=1 for these).
N_BIO_QUERIES = 16
GENERATION_TARGETS = [f"{algo}_q{i}" for algo in ("m1", "m4") for i in range(N_BIO_QUERIES)]
GENERATION_K_RUNS = 1
