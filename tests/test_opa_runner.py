"""E3: real engine success, complete output validation and owned child cleanup."""

import asyncio
import json
import os
import sys
from pathlib import Path

import anyio
import pytest

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.config import EvaluationSettings
from cloud_governance_mcp.engine.opa import (
    OpaEngine,
    run_process,
    validate_engine_report,
)
from cloud_governance_mcp.evaluation_errors import EvaluationCode, EvaluationFailure
from cloud_governance_mcp.json_codec import decode_object
from cloud_governance_mcp.projection import to_evaluation_input

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures/plans"


def request(filename="encrypted_rds.json"):
    snapshot = TerraformPlanAdapter(include_policy_values=True).normalize(
        json.loads((FIXTURES / filename).read_text())
    )
    return to_evaluation_input(snapshot, ["AWS-RDS-001"])


@pytest.mark.parametrize(
    "filename,outcome",
    [
        ("encrypted_rds.json", "pass"),
        ("unencrypted_rds.json", "fail"),
        ("empty.json", None),
    ],
)
async def test_real_engine_returns_explicit_checks(opa_path, filename, outcome):
    engine = OpaEngine(EvaluationSettings(opa_path=str(opa_path)))
    result = await engine.evaluate(request(filename), load_catalog())
    assert [c.outcome for c in result.checks] == ([outcome] if outcome else [])
    assert engine._verified


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.clear(),
        lambda d: d.update(result=[]),
        lambda d: d["result"][0].update(expressions=[]),
        lambda d: d["result"][0]["expressions"][0].update(value=None),
        lambda d: d["result"][0]["expressions"][0]["value"].update(checks=[]),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"].append(
            d["result"][0]["expressions"][0]["value"]["checks"][0].copy()
        ),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"][0].update(
            resource_address="SENTINEL_EXTRA"
        ),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"][0].update(
            outcome="fail"
        ),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"][0].update(
            attribute_path=["SENTINEL_PATH"]
        ),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"][0].update(
            reason_code="SENTINEL_REASON"
        ),
        lambda d: d["result"][0]["expressions"][0]["value"]["checks"][0].update(
            reason_code="RESOURCE_NOT_SUPPORTED",
            outcome="not_applicable",
            attribute_path=[],
        ),
    ],
)
async def test_corrupt_or_incomplete_batch_is_never_accepted(mutate):
    check = dict(
        policy_id="AWS-RDS-001",
        resource_address="aws_db_instance.example",
        outcome="pass",
        reason_code="RDS_ENCRYPTION_ENABLED",
        attribute_path=["storage_encrypted"],
    )
    doc = {
        "result": [
            {"expressions": [{"value": {"schema_version": "1", "checks": [check]}}]}
        ]
    }
    mutate(doc)
    with pytest.raises(EvaluationFailure) as error:
        validate_engine_report(doc, request(), load_catalog())
    assert error.value.code == EvaluationCode.OPA_OUTPUT_INVALID
    assert "SENTINEL_" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":1,"a":2}',
        b'{"x":NaN}',
        b'{"x":1e999}',
        b"\xff",
        b"[]",
        b'{"x":' + b"[" * 129 + b"0" + b"]" * 129 + b"}",
    ],
)
async def test_ambiguous_json_is_rejected(payload):
    with pytest.raises(ValueError):
        decode_object(payload)


async def test_runtime_unavailable_and_input_limits():
    for settings, code in [
        (EvaluationSettings(), EvaluationCode.OPA_NOT_CONFIGURED),
        (
            EvaluationSettings(opa_path="/does/not/exist/opa"),
            EvaluationCode.OPA_NOT_FOUND,
        ),
        (
            EvaluationSettings(max_opa_input_bytes=1),
            EvaluationCode.OPA_INPUT_LIMIT_EXCEEDED,
        ),
    ]:
        with pytest.raises(EvaluationFailure) as error:
            await OpaEngine(settings).evaluate(request(), load_catalog())
        assert error.value.code == code


async def test_child_environment_is_explicit_and_input_is_only_stdin(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPA_EVAL_DATA", "SENTINEL_OVERRIDE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SENTINEL_CREDENTIAL")
    script = "import os,sys,json;print(json.dumps({'env':dict(os.environ),'args':sys.argv[1:],'input':sys.stdin.read()}))"
    raw = await run_process(
        sys.executable,
        ["-I", "-c", script],
        b"fixture input",
        EvaluationSettings(),
        str(tmp_path),
    )
    data = json.loads(raw)
    # macOS may inject this locale marker into any launched process. It is not
    # supplied by our runner; arbitrary inherited environment keys stay absent.
    assert set(data["env"]) <= {"LANG", "LC_ALL", "__CF_USER_TEXT_ENCODING"}
    assert data["env"]["LANG"] == data["env"]["LC_ALL"] == "C"
    assert "SENTINEL_" not in raw.decode()
    assert data["args"] == []
    assert data["input"] == "fixture input"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_output_overflow_reaps_child(tmp_path, stream):
    script = f"import sys;sys.{stream}.write('x'*10000);sys.{stream}.flush()"
    settings = EvaluationSettings(max_opa_output_bytes=50, max_opa_stderr_bytes=50)
    with pytest.raises(EvaluationFailure) as error:
        await run_process(
            sys.executable, ["-I", "-c", script], b"", settings, str(tmp_path)
        )
    assert error.value.code == EvaluationCode.OPA_OUTPUT_LIMIT_EXCEEDED


async def test_timeout_and_repeated_cancellation_kill_and_reap_term_resistant_child(
    tmp_path,
):
    pid_file = tmp_path / "pid"
    script = "import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('pid').write_text(str(os.getpid()));time.sleep(60)"
    task = asyncio.create_task(
        run_process(
            sys.executable,
            ["-I", "-c", script],
            b"",
            EvaluationSettings(),
            str(tmp_path),
        )
    )
    async with asyncio.timeout(5):
        while not pid_file.exists():
            await asyncio.sleep(0.01)
    pid = int(pid_file.read_text())
    task.cancel()
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 4)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


async def test_process_deadline_covers_blocked_stdin_and_no_output(tmp_path):
    with pytest.raises(EvaluationFailure) as error:
        await run_process(
            sys.executable,
            ["-I", "-c", "import time;time.sleep(60)"],
            b"x" * 2_000_000,
            EvaluationSettings(
                opa_eval_timeout_seconds=1, opa_process_timeout_seconds=2
            ),
            str(tmp_path),
        )
    assert error.value.code == EvaluationCode.OPA_TIMEOUT


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_exact_output_limit_succeeds_and_one_byte_over_fails(tmp_path, stream):
    for size in (50, 51):
        script = f"import sys;sys.{stream}.write('x'*{size})"
        settings = EvaluationSettings(max_opa_output_bytes=50, max_opa_stderr_bytes=50)
        if size == 50:
            output = await run_process(
                sys.executable, ["-I", "-c", script], b"", settings, str(tmp_path)
            )
            assert output == (b"x" * 50 if stream == "stdout" else b"")
        else:
            with pytest.raises(EvaluationFailure) as error:
                await run_process(
                    sys.executable, ["-I", "-c", script], b"", settings, str(tmp_path)
                )
            assert error.value.code == EvaluationCode.OPA_OUTPUT_LIMIT_EXCEEDED


async def test_exact_engine_input_budget_and_one_byte_over(opa_path):
    data = request()
    size = len(data.model_dump_json().encode("utf-8"))
    assert (
        await OpaEngine(
            EvaluationSettings(opa_path=str(opa_path), max_opa_input_bytes=size)
        ).evaluate(data, load_catalog())
    ).checks
    with pytest.raises(EvaluationFailure) as error:
        await OpaEngine(
            EvaluationSettings(opa_path=str(opa_path), max_opa_input_bytes=size - 1)
        ).evaluate(data, load_catalog())
    assert error.value.code == EvaluationCode.OPA_INPUT_LIMIT_EXCEEDED


@pytest.mark.parametrize("kind", ["compile", "runtime", "undefined"])
async def test_real_opa_compilation_runtime_and_undefined_failures(
    opa_path, tmp_path, kind
):
    policy = tmp_path / "failure.rego"
    policy.write_text(
        "package failure\nimport rego.v1\n"
        + (
            "SENTINEL_INVALID !!!\n"
            if kind == "compile"
            else "value := input.one\nvalue := input.two\n"
        )
    )
    args = [
        "eval",
        "--format=json",
        "--stdin-input",
        "--strict-builtin-errors",
        "--data",
        str(policy),
        "data.failure.missing" if kind == "undefined" else "data.failure.value",
    ]
    with pytest.raises(EvaluationFailure) as error:
        raw = await run_process(
            str(opa_path),
            args,
            b'{"one":1,"two":2}',
            EvaluationSettings(),
            str(tmp_path),
        )
        validate_engine_report(decode_object(raw), request(), load_catalog())
    assert error.value.code == (
        EvaluationCode.OPA_OUTPUT_INVALID
        if kind == "undefined"
        else EvaluationCode.OPA_EXECUTION_ERROR
    )
    assert "SENTINEL_" not in str(error.value)


async def test_wrong_version_nonexecutable_and_nonzero_exit_are_safe(tmp_path):
    fake = tmp_path / "fake-opa"
    fake.write_text(f"#!{sys.executable}\nprint('Version: 0.0.0')\n")
    fake.chmod(0o755)
    with pytest.raises(EvaluationFailure) as error:
        await OpaEngine(EvaluationSettings(opa_path=str(fake))).evaluate(
            request(), load_catalog()
        )
    assert error.value.code == EvaluationCode.OPA_VERSION_UNSUPPORTED
    fake.chmod(0o644)
    with pytest.raises(EvaluationFailure) as error:
        await OpaEngine(EvaluationSettings(opa_path=str(fake))).evaluate(
            request(), load_catalog()
        )
    assert error.value.code == EvaluationCode.OPA_NOT_FOUND
    with pytest.raises(EvaluationFailure) as error:
        await run_process(
            sys.executable,
            ["-I", "-c", "import sys;sys.stderr.write('SENTINEL_FAILURE');sys.exit(3)"],
            b"",
            EvaluationSettings(),
            str(tmp_path),
        )
    assert error.value.code == EvaluationCode.OPA_EXECUTION_ERROR
    assert "SENTINEL_" not in str(error.value)


async def test_anyio_scope_cancellation_reaps_child_before_returning(tmp_path):
    scopes = []
    script = "import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('scope-pid').write_text(str(os.getpid()));time.sleep(60)"

    async def child():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await run_process(
                sys.executable,
                ["-I", "-c", script],
                b"",
                EvaluationSettings(),
                str(tmp_path),
            )

    async with anyio.create_task_group() as group:
        group.start_soon(child)
        async with asyncio.timeout(5):
            while not (tmp_path / "scope-pid").exists():
                await asyncio.sleep(0.01)
        pid = int((tmp_path / "scope-pid").read_text())
        scopes[0].cancel()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
