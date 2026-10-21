"""Fixed implemented scope guards, shared without asset reads or MCP imports.

The packaged catalog owns public prose/reason templates. These small compiled
allowlists prevent edited assets or injected models from advertising more scope.
"""

POLICY_IDS = ("AWS-RDS-001", "AWS-SG-001")
AWS_PROVIDER = "registry.terraform.io/hashicorp/aws"
RDS_RESOURCE_TYPES = ("aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance")
SSH_TYPES = (
    "aws_security_group",
    "aws_security_group_rule",
    "aws_vpc_security_group_ingress_rule",
)
RESOURCE_TYPES = {"AWS-RDS-001": RDS_RESOURCE_TYPES, "AWS-SG-001": SSH_TYPES}
VERSIONS = {"AWS-RDS-001": "1.1.0", "AWS-SG-001": "1.0.0"}
REQUIRED_PATHS = {
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


def validate_metadata(
    policy_id: str,
    version: str,
    providers: list[str],
    types: list[str],
    paths: list[list[str | int]],
    configuration: list[str],
) -> None:
    """Cross-check fields per ID, not just against a union of valid values."""
    if (
        policy_id not in POLICY_IDS
        or version != VERSIONS[policy_id]
        or providers != [AWS_PROVIDER]
        or types != list(RESOURCE_TYPES[policy_id])
        or paths != REQUIRED_PATHS[policy_id]
        or configuration
    ):
        raise ValueError("Unsupported policy metadata.")
