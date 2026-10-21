package cloud_governance_dispatch_test

import data.cloud_governance as policy
import rego.v1

test_both_policies_have_cross_scope_checks if {
	rds := {"address": "aws_db_instance.example", "mode": "managed", "action_category": "create", "provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_db_instance", "desired_state": {"scope": "standalone", "encryption": {"state": "known", "value": true}}}
	sg := object.union(rds, {"address": "aws_security_group.example", "resource_type": "aws_security_group", "ssh_state": {"representation": "inline", "direction": {"state": "known", "value": "ingress"}, "rules": {"state": "known", "items": []}}})
	r := policy.report with input as {"schema_version": "3", "selected_policy_ids": ["AWS-RDS-001", "AWS-SG-001"], "resources": [rds, sg]}
	r.checks[0].outcome == "pass"
	r.checks[1].outcome == "not_applicable"
	r.checks[2].outcome == "not_applicable"
	r.checks[3].outcome == "pass"
	not r.checks[4]
}

test_old_input_is_undefined if {
	not policy.report with input as {"schema_version": "2", "selected_policy_ids": [], "resources": []}
}
