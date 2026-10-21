# Expanded RDS encryption regressions exercise the packaged policy.
package cloud_governance_m1_test

import data.cloud_governance as policy
import rego.v1

cluster := {
	"address": "module.db.aws_rds_cluster.example[0]",
	"provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_rds_cluster",
	"mode": "managed", "action_category": "no_op",
	"desired_state": {"scope": "cluster", "association": {"state": "not_required"}, "encryption": {"state": "known", "value": true}},
}

member := {
	"address": "module.db.aws_rds_cluster_instance.member[0]",
	"provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_rds_cluster_instance",
	"mode": "managed", "action_category": "no_op",
	"desired_state": {"scope": "cluster_member", "association": {"state": "resolved", "cluster_address": cluster.address}, "encryption": {"state": "unavailable"}},
}

known_outcome(value) := "pass" if value == true

else := "fail"

test_direct_cluster_and_inherited_known_values if {
	every enabled in [true, false] {
		target := object.union(cluster, {"desired_state": {"scope": "cluster", "encryption": {"state": "known", "value": enabled}}})
		results := policy.report with input as {"schema_version": "3", "selected_policy_ids": ["AWS-RDS-001"], "resources": [target, member]}
		results.checks[0].outcome == known_outcome(enabled)
		results.checks[1].outcome == known_outcome(enabled)
		not results.checks[2]
		every check in results.checks {
			check.outcome == known_outcome(enabled)
		}
	}
}

test_all_target_uncertainty_states if {
	every state in ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type"] {
		target := object.union(cluster, {"desired_state": {"scope": "cluster", "encryption": {"state": state}}})
		results := policy.report with input as {"schema_version": "3", "selected_policy_ids": ["AWS-RDS-001"], "resources": [target, member]}
		results.checks[0].outcome == "indeterminate"
		results.checks[1].outcome == "indeterminate"
		not results.checks[2]
		every check in results.checks { check.outcome == "indeterminate" }
	}
}

test_all_unresolved_member_states if {
	every state in ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type", "context_unverified", "not_found", "ambiguous"] {
		r := object.union(member, {"desired_state": {"scope": "cluster_member", "association": {"state": state}, "encryption": {"state": "known", "value": true}}})
		result := policy.report with input as {"schema_version": "3", "selected_policy_ids": ["AWS-RDS-001"], "resources": [r]}
		not result.checks[1]
		result.checks[0].outcome == "indeterminate"
		result.checks[0].attribute_path == ["cluster_identifier"]
	}
}

test_member_copy_does_not_override_cluster if {
	r := object.union(member, {"desired_state": object.union(member.desired_state, {"encryption": {"state": "known", "value": false}})})
	policy.reason(r) == "RDS_CLUSTER_ENCRYPTION_ENABLED" with input as {"resources": [cluster, r]}
}

test_schema_mismatch_is_undefined if {
	not policy.report with input as {"schema_version": "1", "selected_policy_ids": ["AWS-RDS-001"], "resources": []}
}

test_missing_target_does_not_manufacture_a_check if {
	result := policy.report with input as {"schema_version": "3", "selected_policy_ids": ["AWS-RDS-001"], "resources": [member]}

	# The Python input validator rejects this graph; exhaustive result validation
	# additionally prevents trusting a batch where this lookup dropped the member.
	result.checks == []
}
