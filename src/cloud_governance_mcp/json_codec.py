"""Strict, bounded-depth object decoding for packaged data and OPA responses.

Callers enforce byte budgets and translate ValueError to their own fixed codes.
No parser messages from this module belong in public errors or logs.
"""

import json
import math


def decode_object(payload: bytes, *, max_depth: int = 128) -> dict[str, object]:
    """Reject ambiguous JSON before recursive decoding can exhaust the stack."""
    text = payload.decode("utf-8")
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > max_depth:
                raise ValueError("JSON depth exceeded.")
        elif character in "]}":
            depth -= 1

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        """Duplicate keys must not select a different decision by decoder order."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate key.")
            result[key] = value
        return result

    def finite(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite number.")
        return number

    def reject(value: str) -> None:
        raise ValueError("Nonfinite constant.")

    result = json.loads(
        text, object_pairs_hook=unique, parse_float=finite, parse_constant=reject
    )
    if not isinstance(result, dict):
        raise ValueError("Object required.")
    return result
