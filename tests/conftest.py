"""Shared test runtime configuration; analysis-only tests never request OPA."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def rds_graph():
    """Build complete synthetic existing-cluster plans with fake known ARNs.

    New real resources commonly have unknown ARNs; tests replace these fields or
    masks explicitly rather than claiming these no-op fixtures were generated.
    """

    def build(encrypted=True, members=1):
        resources = [
            (
                "aws_rds_cluster",
                "example",
                {
                    "storage_encrypted": encrypted,
                    "cluster_identifier": "demo-cluster",
                    "arn": "arn:aws:rds:us-east-1:111122223333:cluster:demo-cluster",
                },
            ),
            *[
                (
                    "aws_rds_cluster_instance",
                    f"member{i}",
                    {
                        "cluster_identifier": "demo-cluster",
                        "arn": f"arn:aws:rds:us-east-1:111122223333:db:demo-member-{i}",
                        "storage_encrypted": not encrypted,
                    },
                )
                for i in range(members)
            ],
        ]
        changes, inventory = [], []
        for kind, name, values in resources:
            identity = {
                "address": f"{kind}.{name}",
                "type": kind,
                "name": name,
                "provider_name": "registry.terraform.io/hashicorp/aws",
                "mode": "managed",
            }
            changes.append(
                {
                    **identity,
                    "change": {
                        "actions": ["no-op"],
                        "after": values,
                        "after_unknown": {},
                        "after_sensitive": {},
                    },
                }
            )
            inventory.append(
                {**identity, "values": deepcopy(values), "sensitive_values": {}}
            )
        return {
            "format_version": "1.2",
            "complete": True,
            "resource_changes": changes,
            "planned_values": {"root_module": {"resources": inventory}},
        }

    return build


@pytest.fixture
def anyio_backend() -> str:
    """Services explicitly target asyncio, including AnyIO's asyncio backend."""
    return "asyncio"


@pytest.fixture
def opa_path() -> Path:
    """Missing real OPA is an actionable failure for full verification, not a skip."""
    root = Path(__file__).resolve().parent.parent
    path = Path(os.environ.get("CLOUD_GOVERNANCE_OPA", root / ".tools/opa/1.21.2/opa"))
    if not path.is_file():
        pytest.fail("Real OPA is required; follow docs/opa-setup.md.")
    return path.resolve()


@pytest.fixture
def ssh_plan():
    """Synthetic format variants with both sources; these are not AWS exports."""

    def build(representation="modern", **overrides):
        rule = {
            "protocol": "tcp",
            "from_port": 22,
            "to_port": 22,
            "cidr_blocks": ["0.0.0.0/0"],
        }
        if representation == "modern":
            kind = "aws_vpc_security_group_ingress_rule"
            values = {
                "ip_protocol": "tcp",
                "from_port": 22,
                "to_port": 22,
                "cidr_ipv4": "0.0.0.0/0",
            }
            values.update(overrides)
        elif representation == "inline":
            kind = "aws_security_group"
            rule.update(overrides)
            values = {"ingress": [rule]}
        else:
            kind = "aws_security_group_rule"
            values = {"type": "ingress", **rule, **overrides}
        identity = {
            "address": kind + ".example",
            "type": kind,
            "name": "example",
            "mode": "managed",
            "provider_name": "registry.terraform.io/hashicorp/aws",
        }
        return {
            "format_version": "1.2",
            "complete": True,
            "resource_changes": [
                {
                    **identity,
                    "change": {
                        "actions": ["create"],
                        "after": values,
                        "after_unknown": {},
                        "after_sensitive": {},
                    },
                }
            ],
            "planned_values": {
                "root_module": {
                    "resources": [
                        {**identity, "values": deepcopy(values), "sensitive_values": {}}
                    ]
                }
            },
        }

    return build


@pytest.fixture
def tag_plan():
    """Synthetic complete change; no real identifiers, provider or AWS needed."""

    def make(after=..., *, resource_type="aws_instance", unknown=None, sensitive=None):
        if after is ...:
            after = {
                "tags_all": {"Environment": "dev", "Owner": "team", "Project": "demo"}
            }
        return {
            "format_version": "1.2",
            "terraform_version": "1.14.0",
            "complete": True,
            "planned_values": {"root_module": {}},
            "resource_changes": [
                {
                    "address": f"{resource_type}.example",
                    "mode": "managed",
                    "type": resource_type,
                    "name": "example",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "change": {
                        "actions": ["create"],
                        "after": deepcopy(after),
                        "after_unknown": deepcopy(
                            unknown if unknown is not None else {}
                        ),
                        "after_sensitive": deepcopy(
                            sensitive if sensitive is not None else {}
                        ),
                    },
                }
            ],
        }

    return make


@pytest.fixture
def s3_plan():
    """Fresh two-resource synthetic plan; no Terraform execution or credentials."""

    def make():
        return json.loads(
            (Path(__file__).parent / "fixtures/plans/s3_compliant.json").read_text()
        )

    return make
