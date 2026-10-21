# Synthetic value-minimized inputs; no provider values or cloud services.
package cloud_governance_ssh_test

import data.cloud_governance_ssh as policy
import rego.v1

world := {"state": "known", "items": [{"state": "known", "family": 4, "prefix_length": 0}]}
private := {"state": "known", "items": [{"state": "known", "family": 4, "prefix_length": 24}]}
absent := {"state": "absent"}
tcp := {"state": "known", "number": 6}
ports := {"state": "known", "from_port": 22, "to_port": 22}

sources(ipv4) := {"ipv4": ipv4, "ipv6": absent, "prefix_lists": absent, "security_groups": absent, "self_reference": absent}
rule(protocol, interval, source) := {"state": "known", "protocol": protocol, "ports": interval, "sources": source}
projection(items) := {"representation": "inline", "direction": {"state": "known", "value": "ingress"}, "rules": {"state": "known", "items": items}}
resource(p) := {"mode": "managed", "action_category": "create", "provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_security_group", "ssh_state": p}

test_world_tcp_and_range_fail if {
	policy.rule_value(rule(tcp, ports, sources(world))) == "fail"
	policy.rule_value(rule(tcp, {"state": "known", "from_port": 20, "to_port": 23}, sources(world))) == "fail"
}

test_all_protocol_ignores_ports if {
	policy.rule_value(rule({"state": "known", "number": -1}, {"state": "missing"}, sources(world))) == "fail"
}

test_non_ssh_protocol_and_ports_pass if {
	policy.rule_value(rule({"state": "known", "number": 17}, ports, sources(world))) == "pass"
	policy.rule_value(rule(tcp, {"state": "known", "from_port": 443, "to_port": 443}, sources(world))) == "pass"
}

test_ipv6_world_fails if {
	source := object.union(sources(absent), {"ipv6": {"state": "known", "items": [{"state": "known", "family": 6, "prefix_length": 0}]}})
	policy.rule_value(rule(tcp, ports, source)) == "fail"
}

test_known_restricted_source_or_permission_short_circuits if {
	policy.rule_value(rule({"state": "unknown"}, ports, sources(private))) == "pass"
	policy.rule_value(rule({"state": "known", "number": 17}, ports, sources({"state": "sensitive"}))) == "pass"
}

test_self_and_group_reference_sources if {
	group := object.union(sources(absent), {"security_groups": {"state": "present"}})
	self := object.union(sources(absent), {"self_reference": {"state": "known", "value": true}})
	policy.rule_value(rule(tcp, ports, group)) == "pass"
	policy.rule_value(rule(tcp, ports, self)) == "pass"
}

test_prefix_list_does_not_imply_safe if {
	source := object.union(sources(private), {"prefix_lists": {"state": "present"}})
	policy.rule_value(rule(tcp, ports, source)) == "prefix_list_unresolved"
	policy.rule_value(rule({"state": "known", "number": 17}, ports, source)) == "pass"
}

test_no_sources_is_missing if {
	policy.rule_value(rule(tcp, ports, sources(absent))) == "missing"
}

test_known_violation_survives_uncertain_sources if {
	source := object.union(sources(world), {"ipv6": {"state": "sensitive"}, "prefix_lists": {"state": "unknown"}})
	policy.rule_value(rule(tcp, ports, source)) == "fail"
}

test_all_required_uncertainty_states if {
	every state in ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type"] {
		policy.rule_value(rule({"state": state}, ports, sources(world))) == state
	}
}

test_priority_uses_necessary_observations if {
	policy.rule_value(rule({"state": "unknown"}, ports, sources({"state": "sensitive"}))) == "sensitive"
	policy.rule_value(rule(tcp, {"state": "missing"}, sources({"state": "invalid_type"}))) == "missing"
}

test_inline_aggregation_counts_one_resource_reason if {
	fail := rule(tcp, ports, sources(world))
	safe := rule(tcp, ports, sources(private))
	unknown := {"state": "unknown"}
	policy.reason(resource(projection([fail, unknown, fail]))) == "SSH_INLINE_UNRESTRICTED_INGRESS"
	policy.reason(resource(projection([unknown, fail]))) == "SSH_INLINE_UNRESTRICTED_INGRESS"
	policy.reason(resource(projection([safe, unknown]))) == "SSH_INLINE_UNKNOWN"
	policy.reason(resource(projection([]))) == "SSH_INLINE_NO_UNRESTRICTED_INGRESS"
}

test_sensitive_inline_withholds_witnesses if {
	p := {"representation": "inline", "direction": {"state": "known", "value": "ingress"}, "rules": {"state": "sensitive"}}
	policy.reason(resource(p)) == "SSH_INLINE_SENSITIVE"
}

test_exclusions_and_direction_precedence if {
	r := resource(projection([]))
	policy.reason(object.union(r, {"mode": "data", "action_category": "delete"})) == "DATA_SOURCE_SKIPPED"
	policy.reason(object.union(r, {"action_category": "delete"})) == "DELETED_RESOURCE_SKIPPED"
	policy.reason(object.union(r, {"provider_name": "other/provider"})) == "RESOURCE_NOT_SUPPORTED"
	policy.reason(object.union(r, {"resource_type": "aws_vpc_security_group_egress_rule"})) == "RESOURCE_NOT_SUPPORTED"
	egress := {"representation": "legacy", "direction": {"state": "known", "value": "egress"}, "rules": {"state": "known", "items": [{"state": "unavailable"}]}}
	policy.reason(object.union(r, {"resource_type": "aws_security_group_rule", "ssh_state": egress})) == "SSH_EGRESS_SKIPPED"
}
