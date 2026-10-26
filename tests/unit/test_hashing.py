"""Unit tests for deterministic JSON hashing."""

from datetime import datetime, timezone

import pytest

from immune.telemetry.hashing import sha256_json


def test_dictionary_key_order_does_not_change_digest() -> None:
    first = {"run": {"step": 1, "status": "OK"}, "items": [1, 2]}
    second = {"items": [1, 2], "run": {"status": "OK", "step": 1}}

    assert sha256_json(first) == sha256_json(second)


def test_list_order_and_numeric_representation_are_preserved() -> None:
    assert sha256_json([1, 2]) != sha256_json([2, 1])
    assert sha256_json(1) != sha256_json(1.0)
    assert sha256_json(0.0) != sha256_json(-0.0)
    assert sha256_json(True) != sha256_json(1)


def test_nested_unicode_values_follow_json_contract() -> None:
    assert sha256_json({"nested": {"✓": ["東京", 1]}}) == sha256_json(
        {"nested": {"✓": ["東京", 1]}}
    )


def test_digest_is_stable_and_sha256_hex() -> None:
    digest = sha256_json({"value": "immune"})

    assert digest == "3f005b88e83ba4bed4c1a5f79c5cb6f2d5502a4275e70ec4da7689f2441197bf"
    assert len(digest) == 64
    assert digest == digest.lower()


@pytest.mark.parametrize(
    "value",
    [
        object(),
        {1: "non-string key"},
        float("nan"),
        float("inf"),
        float("-inf"),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    ],
)
def test_non_json_values_are_rejected(value: object) -> None:
    with pytest.raises(TypeError):
        sha256_json(value)
