"""Fixed probe roster — never invented by an LLM at runtime.

Each probe's task_scenario states a concrete reuse goal, not an invitation to
be curious: this is what suppresses low-information questions (e.g. "what is
the record ID") without any hardcoded blocklist.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProbeConfig:
    id: str
    mode: Literal["mainstream", "adversarial"]
    role_label: str
    task_scenario: str


PROBES = [
    ProbeConfig(
        id="reproducing_biologist",
        mode="mainstream",
        role_label="Reproducing Biologist",
        task_scenario=(
            "You are a biologist attempting to physically reproduce this "
            "dataset in your own lab, years after the original work, using "
            "your own equipment, reagents, and organisms/specimens. You do "
            "not have access to the original lab's protocols beyond what is "
            "written in the dataset's metadata. Ask what you genuinely need "
            "to know to redo the experiment closely enough to get comparable, "
            "trustworthy results — sample origin and handling, exact "
            "protocol/instrument parameters, environmental conditions, "
            "timing, and anything else that would silently change your "
            "results if you got it wrong."
        ),
    ),
    ProbeConfig(
        id="ml_experiment_designer",
        mode="mainstream",
        role_label="ML Experiment Designer",
        task_scenario=(
            "You are an ML engineer designing a training/evaluation pipeline "
            "that will consume this dataset. You need to decide how to split "
            "the data without leakage, what preprocessing is required, which "
            "fields are usable features vs. identifiers vs. labels, and "
            "whether the data's provenance and collection conditions "
            "introduce biases or confounds your pipeline must account for. "
            "Ask what you need to know about the data's structure, "
            "provenance, and quality to build a correct, non-leaky, "
            "reproducible pipeline around it."
        ),
    ),
    ProbeConfig(
        id="data_analyst",
        mode="mainstream",
        role_label="Data Analyst",
        task_scenario=(
            "You are a data analyst asked to produce a first descriptive "
            "report on this dataset before anyone attempts modeling on it — "
            "group/cohort sizes, whether groups being compared are actually "
            "comparable, distributions and typical ranges of key variables, "
            "missingness patterns, and any potential confounders (batch "
            "effects, collection-site or time differences, demographic "
            "imbalances) that could make a naive comparison misleading. Ask "
            "what you need to know to describe the data honestly and flag "
            "anything that would make a simple group comparison unsound."
        ),
    ),
    ProbeConfig(
        id="decade_later_auditor",
        mode="adversarial",
        role_label="Decade-Later Retraction Auditor",
        task_scenario=(
            "You are auditing this dataset roughly ten years after its "
            "original publication, on behalf of a journal investigating a "
            "possible retraction. The instruments, software versions, and "
            "reference databases in common use have moved on since the "
            "dataset was produced, and the original authors may not be "
            "reachable. Ask what you need to verify authenticity, chain of "
            "custody, and whether the recorded results still hold up under "
            "modern scrutiny — anything that would let you tell a genuine "
            "irregularity apart from an artifact of outdated tooling."
        ),
    ),
]
