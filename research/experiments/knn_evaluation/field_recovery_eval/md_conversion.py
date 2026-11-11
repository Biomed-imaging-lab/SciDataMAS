"""Conversion glue between rag_curator's approved-standard JSON schema, the
m1/m4 generator output shapes, and eval/md_classes.MDField used by the
existing semantic-comparison judge infra.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.md_classes import MDField


def load_approved_standard(path: Path) -> Dict[str, Any]:
    """Parse one rag_curator/tmp_res/approved_tables/*.json (StandardOutput shape).

    The file stem (not standard.standard_id, which repeats across records,
    e.g. "MIGS" appears in both 100_MIMS and 4557_MISAG) is used as the
    unique key for this experiment.
    """
    with open(path, "rt") as fio:
        data = json.load(fio)

    standard = data["standard"]
    gt_fields: Dict[str, MDField] = {}
    for field_name, field in standard["table"]["fields"].items():
        gt_fields[field_name] = MDField(
            name=field["name"],
            descr=field["descr"],
            type=field["type"],
            values=field.get("possible_values"),
        )

    return {
        "standard_key": path.stem,
        "standard_id": standard["standard_id"],
        "name": standard["name"],
        "abstract": standard["abstract"],
        "gt_fields": gt_fields,
    }


def m1_output_to_mdfields(md_schema: Dict[str, Dict[str, str]]) -> Dict[str, MDField]:
    """m1's flat {field_name: {descr, type}} -> Dict[str, MDField]."""
    return {
        fname: MDField(
            name=fname,
            descr=fdata.get("descr", ""),
            type=fdata.get("type", ""),
        )
        for fname, fdata in md_schema.items()
    }


def flatten_m4(fields_per_node: Dict[str, Dict[str, Any]]) -> Dict[str, MDField]:
    """m4's per-DAG-node {node_id: {"md_schema": [{field_id, descr, type,
    allowed_values}, ...]}} -> flat Dict[str, MDField].

    field_id uniqueness across nodes is enforced by m4's own MDGenerationFlow
    validation, so no collision handling is needed here.
    """
    flat: Dict[str, MDField] = {}
    for node_gen in fields_per_node.values():
        for fld in node_gen["md_schema"]:
            values: Optional[List[str]] = fld.get("allowed_values") or None
            flat[fld["field_id"]] = MDField(
                name=fld["field_id"],
                descr=fld.get("descr", ""),
                type=fld.get("type", ""),
                values=values,
            )
    return flat
