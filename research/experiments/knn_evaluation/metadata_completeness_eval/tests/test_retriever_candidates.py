"""Unit test for retriever.py — needs one real embedding API call.

Build a REMBI-derived metadata dict with one field deliberately stripped out,
confirm candidates() excludes it, and a clearly-relevant question scores its
true matching field highest among the remaining ones.

Usage:
    python tests/test_retriever_candidates.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent.parent / "rag_curator" / ".env")

from eval.md_classes import MDField
from retriever import Retriever


def main():
    metadata = {
        "Specimen.preparation_method": MDField(
            name="Specimen.preparation_method",
            descr="The method used to prepare the biological specimen prior to imaging, e.g. fixation, staining, sectioning protocol.",
            type="string",
        ),
        "Study.type": MDField(
            name="Study.type",
            descr="The general category of the study, e.g. hypothesis-driven, exploratory, or diagnostic imaging.",
            type="string",
        ),
        "Biosample.organism": MDField(
            name="Biosample.organism",
            descr="The species of organism the biosample was derived from.",
            type="string",
        ),
    }
    # deliberately stripped: no field about imaging channel/wavelength content

    retriever = Retriever(metadata)

    question = "How was the tissue specimen fixed and prepared before imaging?"
    scores = retriever.score(question)
    candidates = retriever.candidates(scores)

    assert candidates, f"expected at least one candidate, got none. scores={scores}"
    assert candidates[0] == "Specimen.preparation_method", (
        f"expected 'Specimen.preparation_method' to rank first, got {candidates[0]}. scores={scores}"
    )

    unrelated_question = "What wavelength and channel configuration was used to capture fluorescence?"
    unrelated_scores = retriever.score(unrelated_question)
    unrelated_candidates = retriever.candidates(unrelated_scores)
    assert "Specimen.preparation_method" not in unrelated_candidates or unrelated_scores[
        "Specimen.preparation_method"
    ] < scores["Specimen.preparation_method"], "stripped-field proxy check failed"

    print("test_retriever_candidates: PASS")
    print(f"  relevant-question scores: {scores}")
    print(f"  unrelated-question scores: {unrelated_scores}")


if __name__ == "__main__":
    main()
