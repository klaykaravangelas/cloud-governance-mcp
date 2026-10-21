"""M1 contracts reject invented links and member encryption copies."""

import pytest
from pydantic import ValidationError

from cloud_governance_mcp.catalog import load_catalog
from cloud_governance_mcp.models import DesiredStateProjection


@pytest.mark.parametrize(
    "state",
    [
        "sensitive",
        "unknown",
        "unverified",
        "unavailable",
        "missing",
        "null",
        "invalid_type",
        "context_unverified",
        "not_found",
        "ambiguous",
    ],
)
def test_unresolved_members_have_no_target_or_value(state):
    report = DesiredStateProjection(
        scope="cluster_member",
        encryption={"state": "unavailable"},
        association={"state": state},
    )
    assert report.association.model_dump() == {"state": state}
    assert report.encryption.model_dump() == {"state": "unavailable"}


@pytest.mark.parametrize(
    "scope,association,encryption",
    [
        ("cluster_member", {"state": "not_required"}, {"state": "unavailable"}),
        (
            "cluster_member",
            {"state": "unknown", "cluster_address": "SENTINEL"},
            {"state": "unavailable"},
        ),
        ("cluster_member", {"state": "resolved"}, {"state": "unavailable"}),
        (
            "cluster_member",
            {"state": "resolved", "cluster_address": "aws_rds_cluster.target"},
            {"state": "known", "value": True},
        ),
        (
            "cluster",
            {"state": "resolved", "cluster_address": "SENTINEL"},
            {"state": "known", "value": True},
        ),
    ],
)
def test_projection_rejects_invalid_state_address_and_scope_combinations(
    scope, association, encryption
):
    with pytest.raises(ValidationError):
        DesiredStateProjection(
            scope=scope, association=association, encryption=encryption
        )


def test_catalog_advertises_only_implemented_rds_coverage():
    policy = load_catalog().policies[0]
    assert policy.policy_version == "1.1.0"
    assert policy.supported_resource_types == [
        "aws_db_instance",
        "aws_rds_cluster",
        "aws_rds_cluster_instance",
    ]
