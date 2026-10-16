"""Exercise typed mask paths independently from Terraform and provider schemas."""

import pytest

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.normalization import extract_mask_paths, merge_mask_paths


@pytest.mark.parametrize(
    ("mask", "expected"),
    [
        (True, [[]]),
        (False, []),
        ({}, []),
        ([], []),
        ({"credentials": True, "ignored": False}, [["credentials"]]),
        ({"items": [False, {"token": True}]}, [["items", 1, "token"]]),
        ({"0": True, "": True}, [[""], ["0"]]),
        ([True, False, True], [[0], [2]]),
    ],
)
def test_extracts_true_paths(mask: object, expected: list) -> None:
    assert extract_mask_paths(mask, max_depth=8) == expected


def test_union_is_conservative_canonical_and_does_not_mutate_inputs() -> None:
    left = [["credentials", "token"], ["items", 0], ["items", "0"]]
    right = [["credentials"], ["items", 0], ["items", 1, "secret"]]
    assert merge_mask_paths(left, right) == [
        ["credentials"],
        ["items", "0"],
        ["items", 0],
        ["items", 1, "secret"],
    ]
    assert left[0] == ["credentials", "token"]
    assert merge_mask_paths(left, [[]], right) == [[]]


@pytest.mark.parametrize("mask", [None, 0, 1, 1.0, "true", {"a": None}, [0], {0: True}])
def test_malformed_masks_fail_with_safe_errors(mask: object) -> None:
    with pytest.raises(AnalysisError) as failure:
        extract_mask_paths(mask, max_depth=8)
    assert failure.value.code == ErrorCode.INVALID_PLAN


def test_mask_depth_counts_containers_and_bounds_cycles() -> None:
    assert extract_mask_paths({"a": [True]}, max_depth=2) == [["a", 0]]
    with pytest.raises(AnalysisError) as failure:
        extract_mask_paths({"a": [True]}, max_depth=1)
    assert failure.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED
    cycle: dict = {}
    cycle["a"] = cycle
    with pytest.raises(AnalysisError) as failure:
        extract_mask_paths(cycle, max_depth=8)
    assert failure.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED
