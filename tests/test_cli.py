"""Verify startup options and safe subprocess diagnostics without starting AWS."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import cloud_governance_mcp.__main__ as entrypoint
from cloud_governance_mcp.errors import ConfigurationError, UnsupportedPlatformError


def test_repeatable_roots_and_all_limits_preserve_operator_settings(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    settings = entrypoint.parse_settings(
        [
            "--allowed-root",
            str(first),
            "--allowed-root",
            str(second),
            "--max-plan-bytes",
            "101",
            "--max-json-depth",
            "12",
            "--max-resources",
            "3",
            "--max-analysis-bytes",
            "456",
        ]
    )
    assert settings.allowed_roots == [str(first), str(second)]
    assert settings.max_plan_bytes == 101
    assert settings.max_json_depth == 12
    assert settings.max_resources == 3
    assert settings.max_analysis_bytes == 456
    assert not first.exists()  # Parsing alone does not access/create roots.


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--allowed-root"],
        ["--allowed-root", "relative"],
        ["--SENTINEL_UNKNOWN_FLAG", "SENTINEL_VALUE"],
        ["--allowed-root", "/tmp", "--max-plan-bytes", "SENTINEL_BAD_NUMBER"],
        ["--allowed-root", "/tmp", "--max-resources", "0"],
        ["--allowed-root", "/tmp", "--max-json-depth", "-1"],
        ["--allowed-root", "/tmp", "--max-analysis-bytes", "0"],
        ["--allowed-r", "/tmp"],
        ["--allowed-root", "/tmp", "--opa-path", "SENTINEL_RELATIVE"],
        ["--allowed-root", "/tmp", "--max-opa-input-bytes", "0"],
        ["--allowed-root", "/tmp", "--max-opa-output-bytes", "SENTINEL_INVALID"],
        ["--allowed-root", "/tmp", "--max-opa-stderr-bytes", "0"],
        ["--allowed-root", "/tmp", "--max-evaluation-bytes", "-1"],
        [
            "--allowed-root",
            "/tmp",
            "--opa-eval-timeout-seconds",
            "10",
            "--opa-process-timeout-seconds",
            "10",
        ],
    ],
)
def test_argument_failures_have_fixed_diagnostics(
    arguments: list[str], tmp_path: Path
) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-m", "cloud_governance_mcp", *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "Invalid analysis configuration.\n"


def test_nonexistent_root_fails_before_serving(tmp_path: Path) -> None:
    root = tmp_path / "SENTINEL_PRIVATE_ROOT"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "cloud_governance_mcp",
            "--allowed-root",
            str(root),
        ],
        cwd=tmp_path,
        input="",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "Invalid analysis configuration.\n"


@pytest.mark.parametrize(
    "exception", [ConfigurationError(), UnsupportedPlatformError()]
)
def test_loader_startup_failures_are_safe(
    monkeypatch, capsys, tmp_path: Path, exception: Exception
) -> None:
    def fail(settings):
        raise exception

    monkeypatch.setattr(entrypoint, "RestrictedPlanLoader", fail)
    assert entrypoint.main(["--allowed-root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == str(exception) + "\n"


def test_unexpected_startup_failure_has_no_exception_text(
    monkeypatch, caplog, tmp_path: Path
) -> None:
    def fail(settings):
        raise RuntimeError(f"SENTINEL_STARTUP_SECRET {tmp_path}")

    monkeypatch.setattr(entrypoint, "RestrictedPlanLoader", fail)
    assert entrypoint.main(["--allowed-root", str(tmp_path)]) == 1
    assert "INTERNAL_ERROR" in caplog.text
    assert "SENTINEL_" not in caplog.text
    assert str(tmp_path) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_documented_cli_information_exits_successfully(
    option: str, tmp_path: Path
) -> None:
    command = Path(sys.executable).parent / "cloud-governance-mcp"
    assert command.exists()
    result = subprocess.run(
        [str(command), option],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert (
        "--allowed-root" in result.stdout
        if option == "--help"
        else "0.1.0.dev0" in result.stdout
    )


def test_eof_shuts_down_cleanly_without_runtime_binaries(tmp_path: Path) -> None:
    environment = {**os.environ, "PATH": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "cloud_governance_mcp",
            "--allowed-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=environment,
        input="",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
