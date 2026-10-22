"""Fixed implemented scope guards, shared without asset reads or MCP imports.

The packaged catalog owns public prose/reason templates. These small compiled
allowlists prevent edited assets or injected models from advertising more scope.
"""

from cloud_governance_mcp.s3_models import (
    S3_FLAGS,
    S3_LINK_STATES,
    S3_TYPES,
    S3_UNCERTAIN,
)
from cloud_governance_mcp.tag_models import TAG_TYPES

POLICY_IDS = ("AWS-RDS-001", "AWS-S3-001", "AWS-SG-001", "AWS-TAG-001")
AWS_PROVIDER = "registry.terraform.io/hashicorp/aws"
RDS_RESOURCE_TYPES = ("aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance")
SSH_TYPES = (
    "aws_security_group",
    "aws_security_group_rule",
    "aws_vpc_security_group_ingress_rule",
)
RESOURCE_TYPES = {
    "AWS-RDS-001": RDS_RESOURCE_TYPES,
    "AWS-SG-001": SSH_TYPES,
    "AWS-TAG-001": TAG_TYPES,
    "AWS-S3-001": S3_TYPES,
}
VERSIONS = {
    "AWS-S3-001": "1.0.0",
    "AWS-RDS-001": "1.1.0",
    "AWS-SG-001": "1.0.0",
    "AWS-TAG-001": "1.0.0",
}
REQUIRED_PATHS = {
    "AWS-S3-001": [["bucket"], *[[flag] for flag in S3_FLAGS]],
    "AWS-TAG-001": [["tags_all"], ["tags"]],
    "AWS-RDS-001": [["storage_encrypted"], ["cluster_identifier"], ["arn"], ["region"]],
    "AWS-SG-001": [
        [name]
        for name in (
            "ingress",
            "type",
            "protocol",
            "ip_protocol",
            "from_port",
            "to_port",
            "cidr_blocks",
            "ipv6_cidr_blocks",
            "cidr_ipv4",
            "cidr_ipv6",
            "prefix_list_ids",
            "prefix_list_id",
            "self",
            "security_groups",
            "source_security_group_id",
            "referenced_security_group_id",
        )
    ],
}
COMMON_REASONS = frozenset(
    ("DATA_SOURCE_SKIPPED", "DELETED_RESOURCE_SKIPPED", "RESOURCE_NOT_SUPPORTED")
)


SEVERITIES = {
    "AWS-S3-001": "high",
    "AWS-RDS-001": "high",
    "AWS-SG-001": "high",
    "AWS-TAG-001": "medium",
}
# Fixed reason meanings, not policy decisions. The catalog owns all public prose.
TAG_REASON_SPECS = {
    "TAG_" + state: ("indeterminate", [])
    for state in ("SENSITIVE", "UNKNOWN", "UNVERIFIED", "UNAVAILABLE")
}
for _source, _prefix in (("tags_all", "TAG_ALL_"), ("tags", "TAG_RESOURCE_")):
    for _suffix, _outcome in {
        "COMPLIANT": "pass",
        "KEY_MISSING": "fail",
        "KEY_EMPTY": "fail",
        "KEY_SENSITIVE": "indeterminate",
        "KEY_UNKNOWN": "indeterminate",
        "KEY_INVALID_TYPE": "indeterminate",
        "MAP_NULL": "fail",
        "MAP_SENSITIVE": "indeterminate",
        "MAP_UNKNOWN": "indeterminate",
        "MAP_INVALID_TYPE": "indeterminate",
    }.items():
        TAG_REASON_SPECS[_prefix + _suffix] = (_outcome, [_source])
TAG_REASON_SPECS["TAG_RESOURCE_MAP_MISSING"] = ("fail", ["tags"])


def validate_severity(policy_id: str, severity: str) -> None:
    """A medium TAG finding must not broaden existing high-severity policies."""
    if policy_id not in SEVERITIES or severity != SEVERITIES[policy_id]:
        raise ValueError("Invalid policy severity.")


def validate_metadata(
    policy_id: str,
    version: str,
    providers: list[str],
    types: list[str],
    paths: list[list[str | int]],
    configuration: list[str],
    severity: str,
) -> None:
    """Cross-check fields per ID, not just against a union of valid values."""
    validate_severity(policy_id, severity)
    if (
        policy_id not in POLICY_IDS
        or version != VERSIONS[policy_id]
        or providers != [AWS_PROVIDER]
        or types != list(RESOURCE_TYPES[policy_id])
        or paths != REQUIRED_PATHS[policy_id]
        or configuration
        != (["required_tag_keys"] if policy_id == "AWS-TAG-001" else [])
    ):
        raise ValueError("Unsupported policy metadata.")


# Fixed S3 reasons have exact paths; inherited checks always point at bucket.
S3_REASON_SPECS = {}
for _kind in ("BLOCK", "BUCKET"):
    _base = ["bucket"] if _kind == "BUCKET" else []
    S3_REASON_SPECS[f"S3_{_kind}_ENABLED"] = ("pass", _base)
    for _flag in S3_FLAGS:
        for _state in (*S3_UNCERTAIN, "disabled"):
            S3_REASON_SPECS[f"S3_{_kind}_{_flag.upper()}_{_state.upper()}"] = (
                "fail" if _state == "disabled" else "indeterminate",
                _base if _kind == "BUCKET" else [_flag],
            )
for _state in S3_LINK_STATES:
    S3_REASON_SPECS["S3_LINK_" + _state.upper()] = ("indeterminate", ["bucket"])
