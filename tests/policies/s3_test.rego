# Synthetic observations exercise S3 decisions without provider values.
package cloud_governance_s3_test

import data.cloud_governance_s3
import rego.v1

base := {"address": "block", "mode": "managed", "action_category": "create", "provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_s3_bucket_public_access_block"}
known(v) := {"state": "known", "value": v}
block(states) := object.union(base, {"s3_state": {"representation": "block", "flags": states}})

test_all_true_passes if {
	cloud_governance_s3.reason(block([known(true), known(true), known(true), known(true)])) == "S3_BLOCK_ENABLED"
}

test_each_false_fails_with_fixed_flag_order if {
	every entry in [
		{"flags": [known(false), known(true), known(true), known(true)], "code": "S3_BLOCK_BLOCK_PUBLIC_ACLS_DISABLED"},
		{"flags": [known(true), known(false), known(true), known(true)], "code": "S3_BLOCK_IGNORE_PUBLIC_ACLS_DISABLED"},
		{"flags": [known(true), known(true), known(false), known(true)], "code": "S3_BLOCK_BLOCK_PUBLIC_POLICY_DISABLED"},
		{"flags": [known(true), known(true), known(true), known(false)], "code": "S3_BLOCK_RESTRICT_PUBLIC_BUCKETS_DISABLED"},
	] {
		cloud_governance_s3.reason(block(entry.flags)) == entry.code
	}
}

test_failure_precedes_uncertainty if {
	cloud_governance_s3.reason(block([{"state": "sensitive"}, known(true), known(false), {"state": "unknown"}])) == "S3_BLOCK_BLOCK_PUBLIC_POLICY_DISABLED"
}

test_uncertainty_priority_and_first_flag if {
	cloud_governance_s3.reason(block([{"state": "unknown"}, {"state": "invalid_type"}, {"state": "sensitive"}, {"state": "sensitive"}])) == "S3_BLOCK_BLOCK_PUBLIC_POLICY_SENSITIVE"
	cloud_governance_s3.reason(block([{"state": "unknown"}, {"state": "unknown"}, known(true), known(true)])) == "S3_BLOCK_BLOCK_PUBLIC_ACLS_UNKNOWN"
}

test_all_uncertain_states_are_defined if {
	every state in ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type"] {
		r := block([{"state": state}, known(true), known(true), known(true)])
		cloud_governance_s3.reason(r) != "S3_BLOCK_ENABLED"
	}
}

test_bucket_inherits_only_proved_target if {
	target := block([known(true), known(true), known(false), known(true)])
	bucket := object.union(base, {"address": "bucket", "resource_type": "aws_s3_bucket", "s3_state": {"representation": "bucket", "state": "resolved", "block_address": "block"}})
	cloud_governance_s3.reason(bucket) == "S3_BUCKET_BLOCK_PUBLIC_POLICY_DISABLED" with input as {"resources": [bucket, target]}
}

test_unproved_links_are_not_passes if {
	every state in ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type", "not_found", "ambiguous", "context_unverified"] {
		bucket := object.union(base, {"resource_type": "aws_s3_bucket", "s3_state": {"representation": "bucket", "state": state}})
		cloud_governance_s3.reason(bucket) != "S3_BUCKET_ENABLED"
	}
}

test_exclusions_need_no_projection if {
	cloud_governance_s3.reason(object.union(base, {"mode": "data"})) == "DATA_SOURCE_SKIPPED"
	cloud_governance_s3.reason(object.union(base, {"action_category": "delete"})) == "DELETED_RESOURCE_SKIPPED"
	cloud_governance_s3.reason(object.union(base, {"provider_name": "other"})) == "RESOURCE_NOT_SUPPORTED"
	cloud_governance_s3.reason(object.union(base, {"resource_type": "aws_s3_bucket_policy"})) == "RESOURCE_NOT_SUPPORTED"
}

test_undefined_target_cannot_manufacture_a_pass if {
	bucket := object.union(base, {"resource_type": "aws_s3_bucket", "s3_state": {"representation": "bucket", "state": "resolved", "block_address": "missing"}})
	not cloud_governance_s3.reason(bucket) with input as {"resources": [bucket]}
}
