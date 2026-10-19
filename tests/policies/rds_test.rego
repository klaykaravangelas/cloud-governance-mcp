# Test-only policies must never be loaded by the application or its wheel.
package cloud_governance_test

import data.cloud_governance
import rego.v1

base := {
	"address": "module.database.aws_db_instance.example[0]",
	"provider_name": "registry.terraform.io/hashicorp/aws",
	"resource_type": "aws_db_instance",
	"mode": "managed",
	"action_category": "create",
	"desired_state": {"scope": "standalone", "encryption": {"state": "known", "value": true}},
}

test_known_true if {
	cloud_governance.reason(base) == "RDS_ENCRYPTION_ENABLED"
}

test_known_false if {
	r := object.union(base, {"desired_state": {"scope": "standalone", "encryption": {"state": "known", "value": false}}})
	cloud_governance.reason(r) == "RDS_ENCRYPTION_DISABLED"
}

test_encryption_uncertainty if {
	cases := {
		"missing": "RDS_ENCRYPTION_MISSING", "null": "RDS_ENCRYPTION_NULL",
		"unknown": "RDS_ENCRYPTION_UNKNOWN", "sensitive": "RDS_ENCRYPTION_SENSITIVE",
		"unverified": "UNKNOWN_METADATA_INCOMPLETE", "invalid_type": "RDS_ENCRYPTION_INVALID_TYPE",
		"unavailable": "DESIRED_STATE_UNAVAILABLE",
	}
	every state, expected in cases {
		r := object.union(base, {"desired_state": {"scope": "standalone", "encryption": {"state": state}}})
		cloud_governance.reason(r) == expected
	}
}

test_scope_uncertainty_precedes_value if {
	cases := {
		"unknown": "RDS_SCOPE_UNKNOWN", "sensitive": "RDS_SCOPE_SENSITIVE",
		"unverified": "UNKNOWN_METADATA_INCOMPLETE", "unavailable": "DESIRED_STATE_UNAVAILABLE",
		"invalid_type": "RDS_SCOPE_INVALID_TYPE", "cluster_associated": "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED",
	}
	every state, expected in cases {
		r := object.union(base, {"desired_state": {"scope": state, "encryption": {"state": "known", "value": false}}})
		cloud_governance.reason(r) == expected
	}
}

test_exclusions_and_actions if {
	cloud_governance.reason(object.union(base, {"mode": "data", "action_category": "delete"})) == "DATA_SOURCE_SKIPPED"
	cloud_governance.reason(object.union(base, {"action_category": "delete"})) == "DELETED_RESOURCE_SKIPPED"
	cloud_governance.reason(object.union(base, {"resource_type": "aws_rds_cluster"})) == "RESOURCE_NOT_SUPPORTED"
	cloud_governance.reason(object.union(base, {"provider_name": "other/provider"})) == "RESOURCE_NOT_SUPPORTED"
	every action in ["create", "update", "replace", "no_op", "read"] {
		cloud_governance.reason(object.union(base, {"action_category": action})) == "RDS_ENCRYPTION_ENABLED"
	}
}

test_defined_empty_report if {
	result := cloud_governance.report with input as {"selected_policy_ids": ["AWS-RDS-001"], "resources": []}
	result == {"schema_version": "1", "checks": []}
}

test_report_preserves_address_and_catalog_metadata if {
	result := cloud_governance.report with input as {"selected_policy_ids": ["AWS-RDS-001"], "resources": [base]}
	result.checks == [{
		"policy_id": "AWS-RDS-001", "resource_address": base.address,
		"outcome": "pass", "reason_code": "RDS_ENCRYPTION_ENABLED", "attribute_path": ["storage_encrypted"],
	}]
}
