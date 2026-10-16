"""Contained, bounded JSON reads; Terraform semantics belong to the adapter.

Use RestrictedPlanLoader as a context manager so its startup root descriptors
are closed. This synchronous core API must run in a worker thread when the
future asynchronous service integrates it; it must not block the MCP event loop.
Returned documents are sensitive internal data and must never be logged or
returned directly as MCP responses.
"""

import errno
import json
import math
import os
import stat
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Self, cast

from cloud_governance_mcp.config import AnalysisSettings, validate_analysis_settings
from cloud_governance_mcp.errors import (
    AnalysisError,
    ConfigurationError,
    ErrorCode,
    UnsupportedPlatformError,
)
from cloud_governance_mcp.models import validate_analysis_input

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


def _require_secure_open() -> None:
    """Fail closed when the platform lacks descriptor-relative no-follow opens."""
    flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC")
    if (
        sys.platform not in {"darwin", "linux"}
        or not all(hasattr(os, flag) for flag in flags)
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        raise UnsupportedPlatformError()


@dataclass(frozen=True, repr=False)
class _Root:
    """One trusted startup directory; aliases affect matching, not later lookup."""

    configured: Path
    resolved: Path
    descriptor: int


def _directory_flags() -> int:
    """Directories are opened read-only, never followed, and never inherited."""
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_root(configured: str) -> _Root:
    """Resolve operator-selected aliases once, then securely pin the root inode."""
    try:
        resolved = Path(configured).resolve(strict=True)
        # Walk even the resolved startup path without following symlinks. A
        # component replaced after resolve() cannot redirect the final root open.
        with ExitStack() as handles:
            current = os.open("/", _directory_flags())
            handles.callback(os.close, current)
            for component in resolved.parts[1:]:
                current = os.open(component, _directory_flags(), dir_fd=current)
                handles.callback(os.close, current)
            # The caller owns this duplicate; temporary ancestor handles close now.
            descriptor = os.dup(current)
        return _Root(Path(configured), resolved, descriptor)
    except OSError, RuntimeError:
        raise ConfigurationError() from None


def _reject_symlink_or_wrong_kind(parent: int, name: str, *, directory: bool) -> None:
    """Reject known links/special files before opening; open flags still guard races."""
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise AnalysisError(ErrorCode.PATH_NOT_ALLOWED)
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_kind(info.st_mode):
        raise AnalysisError(ErrorCode.PLAN_FILE_UNAVAILABLE)


def _open_component(parent: int, name: str, *, directory: bool) -> int:
    """Keep link refusal atomic, even if a component changes after its stat."""
    try:
        _reject_symlink_or_wrong_kind(parent, name, directory=directory)
        flags = (
            _directory_flags()
            if directory
            else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        descriptor = os.open(name, flags, dir_fd=parent)
    except OSError as error:
        # Some systems return ENOTDIR rather than ELOOP for a directory symlink.
        # This second stat only classifies a failed open; it never authorizes one.
        linked = error.errno == errno.ELOOP
        if error.errno == errno.ENOTDIR:
            try:
                linked = stat.S_ISLNK(
                    os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode
                )
            except OSError:
                pass
        code = ErrorCode.PATH_NOT_ALLOWED if linked else ErrorCode.PLAN_FILE_UNAVAILABLE
        raise AnalysisError(code) from None

    # Validate the opened inode, not merely the pathname observed before open.
    try:
        info = os.fstat(descriptor)
        expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected_kind(info.st_mode):
            raise AnalysisError(ErrorCode.PLAN_FILE_UNAVAILABLE)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _read_bounded(descriptor: int, limit: int) -> bytes:
    """Read at most limit + 1 bytes, so growth or short reads cannot bypass budgets."""
    chunks: list[bytes] = []
    length = 0
    while length <= limit:
        chunk = os.read(descriptor, min(65_536, limit + 1 - length))
        if not chunk:
            break
        chunks.append(chunk)
        length += len(chunk)
    if length > limit:
        raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
    return b"".join(chunks)


def _check_depth(text: str, limit: int) -> None:
    """Bound container depth before json.loads can recurse into untrusted input."""
    stack: list[str] = []
    quoted = False
    escaped = False
    for character in text:
        # Escaped quotes and braces in strings are data, not container delimiters.
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
            stack.append(character)
            if len(stack) > limit:
                raise AnalysisError(ErrorCode.PLAN_LIMIT_EXCEEDED)
        elif character in "]}":
            if not stack or stack.pop() != {"]": "[", "}": "{"}[character]:
                raise ValueError("Mismatched JSON containers.")
    if quoted or stack:
        raise ValueError("Unterminated JSON string or container.")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """Reject duplicate keys rather than silently accepting the last value."""
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are unsupported.")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    """JSON numbers must remain finite after conversion, including large exponents."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON numbers are unsupported.")
    return number


def _reject_constant(value: str) -> JsonValue:
    """Python accepts NaN/Infinity by default, but the JSON contract forbids them."""
    raise ValueError("Non-finite JSON constants are unsupported.")


def _decode_document(payload: bytes, max_depth: int) -> dict[str, JsonValue]:
    """Decode strict UTF-8 JSON with no raw parser details crossing this boundary."""
    try:
        text = payload.decode("utf-8")
        if text.startswith("\ufeff"):
            raise ValueError("UTF-8 BOM is unsupported.")
        _check_depth(text, max_depth)
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_finite_float,
            parse_constant=_reject_constant,
        )
    except UnicodeError, ValueError, RecursionError:
        raise AnalysisError(ErrorCode.INVALID_JSON) from None
    if not isinstance(document, dict):
        raise AnalysisError(ErrorCode.INVALID_PLAN)
    return cast(dict[str, JsonValue], document)


class RestrictedPlanLoader:
    """Read JSON beneath pinned roots; close the loader or use it in a with block.

    Startup validates every configured root. Relative input uses the first root;
    absolute input matches a configured or resolved root alias without resolving
    untrusted path components. The loader does not validate Terraform envelopes.
    """

    def __init__(self, settings: AnalysisSettings) -> None:
        self._settings = validate_analysis_settings(settings)
        _require_secure_open()
        self._lifecycle_lock = Lock()
        self._closed = False
        self._roots: list[_Root] = []
        self._root_handles = ExitStack()
        try:
            for configured in self._settings.allowed_roots:
                root = _open_root(configured)
                self._root_handles.callback(os.close, root.descriptor)
                self._roots.append(root)
        except BaseException:
            # Invalid later roots or interrupted startup must not leak earlier ones.
            self.close()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def close(self) -> None:
        """Release startup descriptors once; active reads own independent duplicates."""
        with self._lifecycle_lock:
            if not self._closed:
                self._closed = True
                self._root_handles.close()

    def _select_root(self, requested: Path) -> tuple[_Root, tuple[str, ...]]:
        """Match components lexically; resolving an untrusted path would follow links."""
        if ".." in requested.parts:
            raise AnalysisError(ErrorCode.PATH_NOT_ALLOWED)
        if not requested.is_absolute():
            return self._roots[0], requested.parts
        selected: tuple[_Root, tuple[str, ...]] | None = None
        specificity = -1
        for root in self._roots:
            for alias in (root.configured, root.resolved):
                if requested.is_relative_to(alias) and len(alias.parts) > specificity:
                    selected = root, requested.relative_to(alias).parts
                    specificity = len(alias.parts)
        if selected is None:
            raise AnalysisError(ErrorCode.PATH_NOT_ALLOWED)
        return selected

    def read_plan(self, plan_path: str) -> dict[str, JsonValue]:
        """Return bounded internal JSON; callers must keep raw values confidential."""
        request = validate_analysis_input({"plan_path": plan_path})
        try:
            with ExitStack() as handles:
                # Serialize root duplication against close(), preventing descriptor
                # reuse from turning a concurrent shutdown into a different root.
                with self._lifecycle_lock:
                    if self._closed:
                        raise AnalysisError(ErrorCode.INTERNAL_ERROR)
                    root, parts = self._select_root(Path(request.plan_path))
                    if not parts:
                        raise AnalysisError(ErrorCode.PLAN_FILE_UNAVAILABLE)
                    current = os.dup(root.descriptor)
                    handles.callback(os.close, current)
                for index, component in enumerate(parts):
                    current = _open_component(
                        current, component, directory=index < len(parts) - 1
                    )
                    handles.callback(os.close, current)
                payload = _read_bounded(current, self._settings.max_plan_bytes)
            # Temporary file/directory descriptors are already closed during parsing.
            return _decode_document(payload, self._settings.max_json_depth)
        except OSError:
            raise AnalysisError(ErrorCode.PLAN_FILE_UNAVAILABLE) from None
