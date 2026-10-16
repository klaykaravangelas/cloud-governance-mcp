"""Run representative on-disk plans through the real contained loader and adapter."""

import shutil
from pathlib import Path

import pytest

from cloud_governance_mcp.adapters.terraform import TerraformPlanAdapter
from cloud_governance_mcp.config import AnalysisSettings
from cloud_governance_mcp.errors import AnalysisError, ErrorCode
from cloud_governance_mcp.files import RestrictedPlanLoader

FIXTURES = Path(__file__).parent / "fixtures" / "plans"


@pytest.mark.parametrize(
    ("filename", "expected_count"),
    [
        ("mixed_nested.json", 7),
        ("empty.json", 0),
        ("partial.json", 1),
        ("unknown_sensitive.json", 2),
        ("encrypted_rds.json", 1),
        ("unencrypted_rds.json", 1),
    ],
)
def test_real_loader_to_adapter(
    filename: str, expected_count: int, tmp_path: Path, caplog
) -> None:
    shutil.copyfile(FIXTURES / filename, tmp_path / filename)
    settings = AnalysisSettings(allowed_roots=[str(tmp_path)])
    adapter = TerraformPlanAdapter(
        max_resources=settings.max_resources, max_depth=settings.max_json_depth
    )
    with RestrictedPlanLoader(settings) as loader:
        snapshot = adapter.normalize(loader.read_plan(filename))
    assert len(snapshot.resources) == expected_count
    assert "SENTINEL_" not in snapshot.model_dump_json()
    assert caplog.text == ""


def test_valid_json_can_still_be_an_invalid_terraform_plan(tmp_path: Path) -> None:
    shutil.copyfile(FIXTURES / "malformed.json", tmp_path / "malformed.json")
    with RestrictedPlanLoader(
        AnalysisSettings(allowed_roots=[str(tmp_path)])
    ) as loader:
        document = loader.read_plan("malformed.json")
        with pytest.raises(AnalysisError) as failure:
            TerraformPlanAdapter().normalize(document)
    assert failure.value.code == ErrorCode.INVALID_PLAN
