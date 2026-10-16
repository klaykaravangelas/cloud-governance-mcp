"""Normalize uncertainty/sensitivity masks without retaining their attribute values."""

from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.models import AttributePath


def merge_mask_paths(*groups: list[AttributePath]) -> list[AttributePath]:
    """Union typed paths, removing descendants already covered by an ancestor.

    A root path [] covers everything. Tagged sort keys keep integer indices and
    string keys distinct and comparable, without guessing from their spelling.
    """
    paths = {tuple(path) for group in groups for path in group}
    ordered = sorted(
        paths,
        key=lambda path: tuple(
            (0, step) if isinstance(step, str) else (1, step) for step in path
        ),
    )
    selected: set[tuple[str | int, ...]] = set()
    result: list[AttributePath] = []
    for path in ordered:
        # Ancestors sort before descendants; prefix membership avoids comparing
        # every path with every other path when a large mask has many siblings.
        if any(path[:length] in selected for length in range(len(path) + 1)):
            continue
        selected.add(path)
        result.append(list(path))
    return result


def extract_mask_paths(mask: object, *, max_depth: int) -> list[AttributePath]:
    """Validate a boolean/container mask and extract its true paths iteratively.

    The adapter supplies a validated positive depth limit. False leaves mark no
    paths; integers such as 0/1 are invalid instead of being coerced to booleans.
    """
    paths: list[AttributePath] = []
    pending: list[tuple[object, AttributePath, int]] = [(mask, [], 0)]
    while pending:
        value, path, depth = pending.pop()
        if type(value) is bool:
            if value:
                paths.append(path)
            continue
        if type(value) not in {dict, list}:
            raise AnalysisError(ErrorCode.INVALID_PLAN)
        if depth + 1 > max_depth:
            raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise AnalysisError(ErrorCode.INVALID_PLAN)
                pending.append((child, [*path, key], depth + 1))
        else:
            for index, child in enumerate(value):
                pending.append((child, [*path, index], depth + 1))
    return merge_mask_paths(paths)
