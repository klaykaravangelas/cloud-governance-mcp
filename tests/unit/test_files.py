"""Exercise real containment, strict JSON decoding, and deterministic race cases."""

import errno
import json
import os
import socket
import stat
import traceback
from pathlib import Path

import pytest

from cloud_governance_mcp import files
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.errors import (
    AnalysisError,
    ConfigurationError,
    ErrorCode,
    UnsupportedPlatformError,
)
from cloud_governance_mcp.files import RestrictedPlanLoader


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Resolve macOS's trusted /var alias before making an isolated test root."""
    directory = tmp_path.resolve() / "allowed"
    directory.mkdir()
    return directory


def settings(root: Path, **limits: int) -> AnalysisSettings:
    """Use real directories while keeping each test's resource budgets explicit."""
    return AnalysisSettings(allowed_roots=[str(root)], **limits)


@pytest.mark.parametrize("absolute", [False, True])
def test_valid_paths_read_json_without_altering_the_file(
    root: Path, absolute: bool
) -> None:
    nested = root / "nested"
    nested.mkdir()
    path = nested / "a plan without extension"
    content = b'{"resource_changes": [], "value": "unchanged"}'
    path.write_bytes(content)
    with RestrictedPlanLoader(settings(root)) as loader:
        selected = str(path) if absolute else "nested/a plan without extension"
        assert loader.read_plan(selected) == {
            "resource_changes": [],
            "value": "unchanged",
        }
    assert path.read_bytes() == content


def test_relative_paths_always_use_the_first_root(root: Path, tmp_path: Path) -> None:
    second = tmp_path.resolve() / "second"
    second.mkdir()
    (root / "plan").write_text('{"root": 1}')
    (second / "plan").write_text('{"root": 2}')
    config = AnalysisSettings(allowed_roots=[str(root), str(second)])
    with RestrictedPlanLoader(config) as loader:
        assert loader.read_plan("plan") == {"root": 1}
        assert loader.read_plan(str(second / "plan")) == {"root": 2}


def test_operator_root_aliases_are_pinned_once(root: Path, tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    (root / "plan").write_text('{"trusted": true}')
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plan").write_text('{"trusted": false}')
    with RestrictedPlanLoader(settings(alias)) as loader:
        # Changing the trusted alias after startup cannot redirect its open handle.
        alias.unlink()
        alias.symlink_to(outside, target_is_directory=True)
        assert loader.read_plan(str(alias / "plan")) == {"trusted": True}
        assert loader.read_plan(str(root / "plan")) == {"trusted": True}


@pytest.mark.parametrize(
    "path", ["../outside/plan", "nested/../plan", "/outside/plan", ".", ""]
)
def test_traversal_external_paths_and_nonfile_roots_are_rejected(
    root: Path, path: str
) -> None:
    with (
        RestrictedPlanLoader(settings(root)) as loader,
        pytest.raises(AnalysisError) as caught,
    ):
        loader.read_plan(path)
    expected = (
        ErrorCode.INVALID_ARGUMENT
        if path == ""
        else ErrorCode.PLAN_FILE_UNAVAILABLE
        if path == "."
        else ErrorCode.PATH_NOT_ALLOWED
    )
    assert caught.value.code == expected


def test_component_prefix_matching_rejects_sibling_directory(root: Path) -> None:
    sibling = root.with_name(root.name + "-other")
    sibling.mkdir()
    target = sibling / "plan"
    target.write_text("{}")
    with (
        RestrictedPlanLoader(settings(root)) as loader,
        pytest.raises(AnalysisError) as caught,
    ):
        loader.read_plan(str(target))
    assert caught.value.code == ErrorCode.PATH_NOT_ALLOWED


@pytest.mark.parametrize("inside", [False, True])
@pytest.mark.parametrize("intermediate", [False, True])
def test_symlinks_are_rejected_even_when_their_target_is_inside(
    root: Path, tmp_path: Path, inside: bool, intermediate: bool
) -> None:
    target = root / "target" if inside else tmp_path / "outside"
    target.mkdir()
    (target / "plan").write_text("{}")
    link = root / "link"
    link.symlink_to(target if intermediate else target / "plan")
    with (
        RestrictedPlanLoader(settings(root)) as loader,
        pytest.raises(AnalysisError) as caught,
    ):
        loader.read_plan("link/plan" if intermediate else "link")
    assert caught.value.code == ErrorCode.PATH_NOT_ALLOWED


@pytest.mark.parametrize("kind", ["missing", "directory", "fifo", "socket"])
def test_nonregular_targets_are_unavailable_without_opening_them(
    root: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = root / "special"
    endpoint = None
    if kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "socket":
        endpoint = socket.socket(socket.AF_UNIX)
        # Relative bind avoids macOS's short AF_UNIX pathname limit in pytest's
        # deeply nested temporary directory, while creating the real target inode.
        monkeypatch.chdir(root)
        endpoint.bind("special")
    try:
        with RestrictedPlanLoader(settings(root)) as loader:
            # Opening a FIFO could hang without NONBLOCK. Known special files
            # should be rejected by lstat before any target open occurs at all.
            def unexpected_open(*args: object, **kwargs: object) -> int:
                pytest.fail("A known special target must not be opened.")

            monkeypatch.setattr(files.os, "open", unexpected_open)
            with pytest.raises(AnalysisError) as caught:
                loader.read_plan("special")
            assert caught.value.code == ErrorCode.PLAN_FILE_UNAVAILABLE
    finally:
        if endpoint is not None:
            endpoint.close()


def test_device_inode_is_rejected_before_open(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with RestrictedPlanLoader(settings(root)) as loader:
        monkeypatch.setattr(
            files.os,
            "stat",
            lambda *args, **kwargs: os.stat_result(
                (stat.S_IFCHR, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            ),
        )
        monkeypatch.setattr(
            files.os, "open", lambda *args, **kwargs: pytest.fail("Device opened")
        )
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("device")
        assert caught.value.code == ErrorCode.PLAN_FILE_UNAVAILABLE


@pytest.mark.parametrize("directory", [False, True])
def test_component_swapped_to_symlink_between_stat_and_open_cannot_escape(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: bool
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plan").write_text('{"SECRET": true}')
    victim = root / ("nested" if directory else "plan")
    if directory:
        victim.mkdir()
        (victim / "plan").write_text("{}")
    else:
        victim.write_text("{}")
    original_open = os.open
    with RestrictedPlanLoader(settings(root)) as loader:

        def swap_then_open(name: str, flags: int, *, dir_fd: int) -> int:
            if name == victim.name:
                victim.rename(root / "original")
                victim.symlink_to(outside if directory else outside / "plan")
            return original_open(name, flags, dir_fd=dir_fd)

        monkeypatch.setattr(files.os, "open", swap_then_open)
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("nested/plan" if directory else "plan")
        assert caught.value.code == ErrorCode.PATH_NOT_ALLOWED


def test_open_directory_handle_survives_later_pathname_replacement(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = root / "nested"
    nested.mkdir()
    (nested / "plan").write_text('{"trusted": true}')
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plan").write_text('{"trusted": false}')
    original_open = os.open
    with RestrictedPlanLoader(settings(root)) as loader:

        def move_after_open(name: str, flags: int, *, dir_fd: int) -> int:
            descriptor = original_open(name, flags, dir_fd=dir_fd)
            if name == "nested":
                nested.rename(root / "original")
                nested.symlink_to(outside)
            return descriptor

        monkeypatch.setattr(files.os, "open", move_after_open)
        assert loader.read_plan("nested/plan") == {"trusted": True}


@pytest.mark.parametrize("payload", [b"{}", b'{"value":"\xc3\xa9"}'])
def test_byte_limit_accepts_exact_size_and_rejects_one_less(
    root: Path, payload: bytes
) -> None:
    (root / "plan").write_bytes(payload)
    with RestrictedPlanLoader(settings(root, max_plan_bytes=len(payload))) as loader:
        assert isinstance(loader.read_plan("plan"), dict)
    with RestrictedPlanLoader(
        settings(root, max_plan_bytes=len(payload) - 1)
    ) as loader:
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED


def test_short_reads_and_file_growth_do_not_bypass_byte_limit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "plan").write_text("{}")
    original_read = os.read
    with RestrictedPlanLoader(settings(root, max_plan_bytes=2)) as loader:
        read_bytes = 0

        def one_byte_read(descriptor: int, size: int) -> bytes:
            nonlocal read_bytes
            data = original_read(descriptor, min(size, 1))
            read_bytes += len(data)
            if read_bytes == 2:
                with (root / "plan").open("a") as stream:
                    stream.write(" ")
            return data

        monkeypatch.setattr(files.os, "read", one_byte_read)
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED
        assert read_bytes == 3  # At most the limit plus the overflow sentinel byte.


@pytest.mark.parametrize(
    ("text", "depth"),
    [("{}", 1), ('{"value": {}}', 2), ('{"value": [[], {}]}', 3)],
)
def test_container_depth_is_bounded_before_decoding(
    root: Path, text: str, depth: int
) -> None:
    (root / "plan").write_text(text)
    with RestrictedPlanLoader(settings(root, max_json_depth=depth)) as loader:
        assert loader.read_plan("plan") == json.loads(text)
    if depth > 1:
        with RestrictedPlanLoader(settings(root, max_json_depth=depth - 1)) as loader:
            with pytest.raises(AnalysisError) as caught:
                loader.read_plan("plan")
            assert caught.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED


def test_braces_quotes_and_backslashes_in_strings_are_not_containers(
    root: Path,
) -> None:
    document = {"text": '[[{ \\"quotes" \\\\ }]]'}
    (root / "plan").write_text(json.dumps(document))
    with RestrictedPlanLoader(settings(root, max_json_depth=1)) as loader:
        assert loader.read_plan("plan") == document


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"{]",
        b'{"SECRET":',
        b'{"x":"unterminated}',
        b"{} {}",
        b'{"x":\xff}',
        b"\xef\xbb\xbf{}",
        b"\xff\xfe{\x00}",
        b'{"SECRET": 1, "SECRET": 2}',
        b'{"x":{"y":1,"y":2}}',
        b'{"x": NaN}',
        b'{"x": Infinity}',
        b'{"x": -Infinity}',
        b'{"x":1e999}',
        b'{"x":-1e999}',
    ],
)
def test_invalid_json_has_safe_errors_and_no_logs(
    root: Path, payload: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    (root / "SECRET_FILENAME").write_bytes(payload)
    with (
        RestrictedPlanLoader(settings(root)) as loader,
        pytest.raises(AnalysisError) as caught,
    ):
        loader.read_plan("SECRET_FILENAME")
    assert caught.value.code == ErrorCode.INVALID_JSON
    diagnostic = "".join(traceback.format_exception(caught.value))
    assert "SECRET_FILENAME" not in str(caught.value)
    assert "SECRET" not in diagnostic.split("AnalysisError:")[-1]
    assert caught.value.__suppress_context__
    assert caplog.records == []


@pytest.mark.parametrize("text", ["[]", "null", "true", "123", '"plan"'])
def test_valid_json_with_nonobject_root_is_not_a_plan(root: Path, text: str) -> None:
    (root / "plan").write_text(text)
    with (
        RestrictedPlanLoader(settings(root)) as loader,
        pytest.raises(AnalysisError) as caught,
    ):
        loader.read_plan("plan")
    assert caught.value.code == ErrorCode.INVALID_PLAN


@pytest.mark.parametrize("kind", ["missing", "file", "loop"])
def test_invalid_startup_roots_fail_without_exposing_paths(
    tmp_path: Path, kind: str
) -> None:
    target = tmp_path / "PRIVATE_ROOT"
    if kind == "file":
        target.write_text("{}")
    elif kind == "loop":
        target.symlink_to(target)
    with pytest.raises(ConfigurationError) as caught:
        RestrictedPlanLoader(settings(target))
    assert str(caught.value) == "Invalid analysis configuration."


def test_no_roots_and_unsupported_platform_fail_before_opening(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ConfigurationError):
        RestrictedPlanLoader({"allowed_roots": []})
    monkeypatch.setattr(files.sys, "platform", "win32")
    with pytest.raises(UnsupportedPlatformError, match="unsupported on this platform"):
        RestrictedPlanLoader(settings(root))


def test_missing_secure_open_flag_has_no_insecure_fallback(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(files.os, "O_NOFOLLOW")
    with pytest.raises(UnsupportedPlatformError):
        RestrictedPlanLoader(settings(root))


def test_read_and_startup_failures_close_all_temporary_handles(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "plan").write_text("{}")
    original_open, original_dup, original_close, original_read = (
        os.open,
        os.dup,
        os.close,
        os.read,
    )
    opened: set[int] = set()

    def track_open(*args: object, **kwargs: object) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.add(descriptor)
        return descriptor

    def track_dup(descriptor: int) -> int:
        duplicated = original_dup(descriptor)
        opened.add(duplicated)
        return duplicated

    def track_close(descriptor: int) -> None:
        original_close(descriptor)
        opened.discard(descriptor)

    monkeypatch.setattr(files.os, "open", track_open)
    monkeypatch.setattr(files.os, "dup", track_dup)
    monkeypatch.setattr(files.os, "close", track_close)
    monkeypatch.setattr(files.os, "supports_dir_fd", {*os.supports_dir_fd, track_open})
    config = AnalysisSettings(allowed_roots=[str(root), str(root / "missing")])
    with pytest.raises(ConfigurationError):
        RestrictedPlanLoader(config)
    assert opened == set()
    with RestrictedPlanLoader(settings(root)) as loader:
        roots = opened.copy()

        def unreadable(descriptor: int, size: int) -> bytes:
            raise PermissionError(errno.EACCES, "PRIVATE_READ_DETAIL")

        monkeypatch.setattr(files.os, "read", unreadable)
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_FILE_UNAVAILABLE
        assert opened == roots
        assert "PRIVATE" not in str(caught.value)
        # Parsing failure and success must leave only startup handles too.
        monkeypatch.setattr(files.os, "read", original_read)
        (root / "plan").write_text("{")
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.INVALID_JSON
        assert opened == roots
        (root / "plan").write_text("{}")
        assert loader.read_plan("plan") == {}
        assert opened == roots

        class InterruptedRead(BaseException):
            """Emulate interruption without sending an operating system signal."""

        def interrupted(descriptor: int, size: int) -> bytes:
            raise InterruptedRead()

        monkeypatch.setattr(files.os, "read", interrupted)
        with pytest.raises(InterruptedRead):
            loader.read_plan("plan")
        assert opened == roots
    assert opened == set()
    loader.close()  # Closing twice must not close a descriptor reused elsewhere.
    with pytest.raises(AnalysisError) as caught:
        loader.read_plan("plan")
    assert caught.value.code == ErrorCode.INTERNAL_ERROR


def test_file_swapped_to_fifo_is_nonblocking_and_never_read(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim = root / "plan"
    victim.write_text("{}")
    original_open = os.open
    with RestrictedPlanLoader(settings(root)) as loader:

        def swap_to_fifo(name: str, flags: int, *, dir_fd: int) -> int:
            victim.unlink()
            os.mkfifo(victim)
            assert flags & os.O_NONBLOCK
            return original_open(name, flags, dir_fd=dir_fd)

        monkeypatch.setattr(files.os, "open", swap_to_fifo)
        monkeypatch.setattr(files.os, "read", lambda *args: pytest.fail("FIFO read"))
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_FILE_UNAVAILABLE


def test_open_permission_errors_do_not_expose_paths(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "plan").write_text("{}")
    with RestrictedPlanLoader(settings(root)) as loader:

        def denied(*args: object, **kwargs: object) -> int:
            raise PermissionError(errno.EACCES, "SECRET_PERMISSION_PATH")

        monkeypatch.setattr(files.os, "open", denied)
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_FILE_UNAVAILABLE
        assert "SECRET_PERMISSION_PATH" not in str(caught.value)


def test_explicit_nested_root_uses_the_most_specific_absolute_alias(
    root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "also-allowed"
    outside.mkdir()
    (outside / "plan").write_text('{"trusted": true}')
    alias = root / "explicit-root"
    alias.symlink_to(outside)
    config = AnalysisSettings(allowed_roots=[str(root), str(alias)])
    with RestrictedPlanLoader(config) as loader:
        assert loader.read_plan(str(alias / "plan")) == {"trusted": True}
        # Relative paths always start at root 1 and may not traverse a symlink
        # below it; explicit root 2 must be addressed by its absolute alias.
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("explicit-root/plan")
        assert caught.value.code == ErrorCode.PATH_NOT_ALLOWED


def test_excessive_nesting_is_rejected_before_json_decoder_runs(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "plan").write_text('{"x":' + "[" * 2000 + "]" * 2000 + "}")
    with RestrictedPlanLoader(settings(root)) as loader:
        monkeypatch.setattr(
            files.json, "loads", lambda *args, **kwargs: pytest.fail("Decoder called")
        )
        with pytest.raises(AnalysisError) as caught:
            loader.read_plan("plan")
        assert caught.value.code == ErrorCode.PLAN_LIMIT_EXCEEDED
