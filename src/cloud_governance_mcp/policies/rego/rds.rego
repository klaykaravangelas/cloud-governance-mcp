# RDS encryption decisions use only the fixed, value-minimized projection.
package cloud_governance

import rego.v1

scope_codes := {
	"sensitive": "RDS_SCOPE_SENSITIVE", "unknown": "RDS_SCOPE_UNKNOWN",
	"unverified": "UNKNOWN_METADATA_INCOMPLETE", "unavailable": "DESIRED_STATE_UNAVAILABLE",
	"invalid_type": "RDS_SCOPE_INVALID_TYPE", "cluster_associated": "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED",
}

direct_codes := {
	"sensitive": "RDS_ENCRYPTION_SENSITIVE", "unknown": "RDS_ENCRYPTION_UNKNOWN",
	"unverified": "UNKNOWN_METADATA_INCOMPLETE", "unavailable": "DESIRED_STATE_UNAVAILABLE",
	"missing": "RDS_ENCRYPTION_MISSING", "null": "RDS_ENCRYPTION_NULL",
	"invalid_type": "RDS_ENCRYPTION_INVALID_TYPE",
}

link_codes := {
	"sensitive": "RDS_CLUSTER_LINK_SENSITIVE", "unknown": "RDS_CLUSTER_LINK_UNKNOWN",
	"unverified": "RDS_CLUSTER_LINK_UNVERIFIED", "unavailable": "RDS_CLUSTER_LINK_UNAVAILABLE",
	"missing": "RDS_CLUSTER_LINK_MISSING", "null": "RDS_CLUSTER_LINK_NULL",
	"invalid_type": "RDS_CLUSTER_LINK_INVALID_TYPE", "context_unverified": "RDS_CLUSTER_LINK_CONTEXT_UNVERIFIED",
	"not_found": "RDS_CLUSTER_LINK_NOT_FOUND", "ambiguous": "RDS_CLUSTER_LINK_AMBIGUOUS",
}

inherited_codes := {
	"sensitive": "RDS_CLUSTER_ENCRYPTION_SENSITIVE", "unknown": "RDS_CLUSTER_ENCRYPTION_UNKNOWN",
	"unverified": "RDS_CLUSTER_ENCRYPTION_UNVERIFIED", "unavailable": "RDS_CLUSTER_ENCRYPTION_UNAVAILABLE",
	"missing": "RDS_CLUSTER_ENCRYPTION_MISSING", "null": "RDS_CLUSTER_ENCRYPTION_NULL",
	"invalid_type": "RDS_CLUSTER_ENCRYPTION_INVALID_TYPE",
}

# One address index avoids scanning the full graph for each cluster member.
resources_by_address := {r.address: r | some r in input.resources}

direct_reason(r) := code if {
	code := scope_codes[r.desired_state.scope]
}

else := code if {
	code := direct_codes[r.desired_state.encryption.state]
}

else := "RDS_ENCRYPTION_ENABLED" if {
	r.desired_state.encryption.value == true
}

else := "RDS_ENCRYPTION_DISABLED" if {
	r.desired_state.encryption.value == false
}

member_reason(r) := code if {
	code := link_codes[r.desired_state.association.state]
}

else := inherited_codes[target.desired_state.encryption.state] if {
	target := resources_by_address[r.desired_state.association.cluster_address]
} else := "RDS_CLUSTER_ENCRYPTION_ENABLED" if {
	target := resources_by_address[r.desired_state.association.cluster_address]
	target.desired_state.encryption.value == true
} else := "RDS_CLUSTER_ENCRYPTION_DISABLED" if {
	target := resources_by_address[r.desired_state.association.cluster_address]
	target.desired_state.encryption.value == false
}

reason(r) := "DATA_SOURCE_SKIPPED" if {
	r.mode == "data"
}

else := "DELETED_RESOURCE_SKIPPED" if {
	r.action_category == "delete"
}

else := "RESOURCE_NOT_SUPPORTED" if {
	r.provider_name != "registry.terraform.io/hashicorp/aws"
}

else := "RESOURCE_NOT_SUPPORTED" if {
	r.resource_type != "aws_db_instance"
	r.resource_type != "aws_rds_cluster"
	r.resource_type != "aws_rds_cluster_instance"
} else := member_reason(r) if {
	r.resource_type == "aws_rds_cluster_instance"
}

else := direct_reason(r) if {
	r.resource_type != "aws_rds_cluster_instance"
}

# Undefined/unsupported input schemas cannot accidentally produce an empty pass.
report := {"schema_version": "1", "checks": checks} if {
	input.schema_version == "5"
	checks := [check |
		some policy_id in input.selected_policy_ids
		some policy in data.cloud_governance_catalog.policies
		policy.policy_id == policy_id
		policy.enabled == true
		some resource in input.resources
		code := policy_reason(policy_id, resource)
		template := policy.reasons[code]
		check := {
			"policy_id": policy_id, "resource_address": resource.address,
			"outcome": template.outcome, "reason_code": code,
			"attribute_path": policy_path(policy_id, resource, template),
		}
	]
}

# Fixed dispatch; requests cannot inject queries or policy definitions.
policy_reason(id, r) := reason(r) if id == "AWS-RDS-001"

else := code if {
	id == "AWS-S3-001"
	code := data.cloud_governance_s3.reason(r)
}

else := data.cloud_governance_ssh.reason(r) if id == "AWS-SG-001"

else := code if {
	id == "AWS-TAG-001"
	result := data.cloud_governance_tags.decision(r)
	code := result.code
}

# Only TAG derives a path from configured key observations; old paths stay fixed.
policy_path(id, r, template) := path if {
	id == "AWS-TAG-001"
	result := data.cloud_governance_tags.decision(r)
	path := result.path
} else := template.attribute_path if id != "AWS-TAG-001"
