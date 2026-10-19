# Desired-state checks only. Scope/uncertainty rules precede boolean decisions.
package cloud_governance

import rego.v1

reason(r) := "DATA_SOURCE_SKIPPED" if {
	r.mode == "data"
} else := "DELETED_RESOURCE_SKIPPED" if {
	r.action_category == "delete"
} else := "RESOURCE_NOT_SUPPORTED" if {
	r.provider_name != "registry.terraform.io/hashicorp/aws"
} else := "RESOURCE_NOT_SUPPORTED" if {
	r.resource_type != "aws_db_instance"
} else := "RDS_SCOPE_SENSITIVE" if {
	r.desired_state.scope == "sensitive"
} else := "RDS_SCOPE_UNKNOWN" if {
	r.desired_state.scope == "unknown"
} else := "UNKNOWN_METADATA_INCOMPLETE" if {
	r.desired_state.scope == "unverified"
} else := "DESIRED_STATE_UNAVAILABLE" if {
	r.desired_state.scope == "unavailable"
} else := "RDS_SCOPE_INVALID_TYPE" if {
	r.desired_state.scope == "invalid_type"
} else := "RDS_CLUSTER_ASSOCIATION_UNSUPPORTED" if {
	r.desired_state.scope == "cluster_associated"
} else := "RDS_ENCRYPTION_SENSITIVE" if {
	r.desired_state.encryption.state == "sensitive"
} else := "RDS_ENCRYPTION_UNKNOWN" if {
	r.desired_state.encryption.state == "unknown"
} else := "UNKNOWN_METADATA_INCOMPLETE" if {
	r.desired_state.encryption.state == "unverified"
} else := "DESIRED_STATE_UNAVAILABLE" if {
	r.desired_state.encryption.state == "unavailable"
} else := "RDS_ENCRYPTION_MISSING" if {
	r.desired_state.encryption.state == "missing"
} else := "RDS_ENCRYPTION_NULL" if {
	r.desired_state.encryption.state == "null"
} else := "RDS_ENCRYPTION_INVALID_TYPE" if {
	r.desired_state.encryption.state == "invalid_type"
} else := "RDS_ENCRYPTION_ENABLED" if {
	r.desired_state.encryption.state == "known"
	r.desired_state.encryption.value == true
} else := "RDS_ENCRYPTION_DISABLED" if {
	r.desired_state.encryption.state == "known"
	r.desired_state.encryption.value == false
}

# A defined report exists even for an empty plan. Python verifies exhaustive
# pair membership: undefined rules cannot silently remove required checks.
report := {"schema_version": "1", "checks": checks} if {
	checks := [check |
		some policy_id in input.selected_policy_ids
		some policy in data.cloud_governance_catalog.policies
		policy.policy_id == policy_id
		policy.enabled == true
		some resource in input.resources
		code := reason(resource)
		template := policy.reasons[code]
		check := {
			"policy_id": policy_id,
			"resource_address": resource.address,
			"outcome": template.outcome,
			"reason_code": code,
			"attribute_path": template.attribute_path,
		}
	]
}
