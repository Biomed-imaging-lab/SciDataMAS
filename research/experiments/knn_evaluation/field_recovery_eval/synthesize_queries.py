"""Stage 1: for each approved standard, synthesize K blind experiment
descriptions (no mention of the standard's name/id) that a downstream
generator will be asked to design a metadata table for.

Usage:
    python synthesize_queries.py
"""

import json
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / "rag_curator" / ".env")

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import config
from md_conversion import load_approved_standard


class SynthQuery(BaseModel):
    topic: str = Field(description="Short, specific research-topic title", default="")
    field_of_science: str = Field(description="Field/subfield label(s)", default="")
    llm_query: str = Field(
        description="Full blind experiment description, never naming the source standard",
        default="",
    )


class SynthQueryBank(BaseModel):
    queries: List[SynthQuery] = Field(default_factory=list)


def read_prompts(path: Path) -> str:
    return path.read_text()


def build_chain():
    system_prompt = read_prompts(config.QUERY_SYNTHESIS_PROMPT_PATH)
    chat = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("placeholder", "{messages}")], "f-string"
    )
    llm = init_chat_model(
        config.SYNTH_MODEL, model_provider=config.SYNTH_PROVIDER, temperature=config.SYNTH_TEMPERATURE
    )
    return chat | llm.with_structured_output(SynthQueryBank, method="json_schema", strict=False)


def synthesize_for_standard(chain, name: str, standard_id: str, abstract: str, k: int) -> SynthQueryBank:
    user_msg = (
        f'Standard identifiers to NEVER mention (avoid also close variants/abbreviations): '
        f'"{name}" (id: "{standard_id}").\n\n'
        f"Abstract describing the kind of data/research this standard covers "
        f"(scrub any of the above identifiers out of your understanding of it):\n{abstract}\n\n"
        f"Generate exactly {k} distinct blind experiment descriptions as specified."
    )
    return chain.invoke({"messages": [("user", user_msg)]})


def main():
    config.QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    chain = build_chain()

    standard_paths = sorted(config.APPROVED_TABLES_DIR.glob("*.json"))
    print(f"Found {len(standard_paths)} approved standards.")

    for path in standard_paths:
        out_path = config.QUERIES_DIR / f"{path.stem}.json"
        if out_path.exists():
            print(f"[skip] {path.stem} (already synthesized)")
            continue

        info = load_approved_standard(path)
        print(f"[synthesize] {info['standard_key']} ({info['name']})")

        bank = synthesize_for_standard(
            chain, info["name"], info["standard_id"], info["abstract"], config.K_QUERIES
        )

        out_path.write_text(
            json.dumps([q.model_dump() for q in bank.queries], indent=2, ensure_ascii=False)
        )


if __name__ == "__main__":
    main()
