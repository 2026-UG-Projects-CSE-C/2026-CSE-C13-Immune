"""Deterministic hashing helpers for telemetry values."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


def sha256_json(value: object) -> str:
    """Return a SHA-256 digest of deterministic serialized JSON.

    Object keys are sorted recursively, and compact separators make dictionary
    insertion order irrelevant. List order and numeric representation are
    preserved; this is not an RFC 8785 semantic-normalization implementation.
    Non-JSON values and non-string object keys are rejected.
    """
    normalized = _normalize_json(value)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON does not support non-finite floats")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            normalized[key] = _normalize_json(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json(item) for item in value]
    raise TypeError(f"value of type {type(value).__name__} is not JSON-compatible")
