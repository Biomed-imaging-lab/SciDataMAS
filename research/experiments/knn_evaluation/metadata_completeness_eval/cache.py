"""(model, prompt_hash) -> response JSON cache, so reruns during development
(e.g. resuming after a follow-up-only failure) don't re-bill identical calls.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict

import config


def _key(model: str, payload: Dict[str, Any]) -> str:
    blob = json.dumps({"model": model, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cached_call(model: str, payload: Dict[str, Any], fn: Callable[[], Any], to_dict, from_dict):
    """fn() must return an object serializable via to_dict/from_dict (both
    plain functions, e.g. pydantic model .model_dump()/(**d))."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = config.CACHE_DIR / f"{_key(model, payload)}.json"
    if cache_path.exists():
        return from_dict(json.loads(cache_path.read_text()))
    result = fn()
    cache_path.write_text(json.dumps(to_dict(result), default=str))
    return result
