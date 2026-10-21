# Direct SSH exposure uses only the fixed, value-minimized observations.
package cloud_governance_ssh

import rego.v1

uncertainty_order := ["sensitive", "unknown", "unverified", "unavailable", "missing", "null", "invalid_type", "prefix_list_unresolved"]

# Fixed branch order avoids depending on source/rule iteration order.
priority(states) := "sensitive" if states.sensitive

else := "unknown" if states.unknown

else := "unverified" if states.unverified

else := "unavailable" if states.unavailable

else := "missing" if states.missing

else := "null" if states.null

else := "invalid_type" if states.invalid_type

else := "prefix_list_unresolved" if states.prefix_list_unresolved

else := "missing"

ssh_value(r) := "yes" if r.protocol.number == -1

else := "yes" if {
	r.protocol.number == 6
	r.ports.state == "known"
	r.ports.from_port <= 22
	22 <= r.ports.to_port
} else := "no" if {
	r.protocol.state == "known"
	r.protocol.number != -1
	r.protocol.number != 6
} else := "no" if {
	r.protocol.number == 6
	r.ports.state == "known"
} else := r.protocol.state if r.protocol.state != "known"

else := r.ports.state

cidrs_safe(observation) if observation.state == "absent"

else if {
	observation.state == "known"
	every item in observation.items {
		item.state == "known"
		item.prefix_length != 0
	}
}

valid_source(s) if {
	some field in [s.ipv4, s.ipv6]
	some item in field.items
	item.state == "known"
}

valid_source(s) if s.security_groups.state == "present"
valid_source(s) if s.self_reference.value == true

source_state(s, state) if {
	some field in [s.ipv4, s.ipv6, s.prefix_lists]
	field.state == state
}

source_state(s, state) if {
	some field in [s.ipv4, s.ipv6]
	some item in field.items
	item.state == state
}

source_state(s, state) if {
	state == "prefix_list_unresolved"
	s.prefix_lists.state == "present"
}

source_state(s, state) if {
	not valid_source(s)
	some field in [s.security_groups, s.self_reference]
	field.state == state
}

world_value(r) := "yes" if {
	some field in [r.sources.ipv4, r.sources.ipv6]
	some item in field.items
	item.state == "known"
	item.prefix_length == 0
} else := "no" if {
	cidrs_safe(r.sources.ipv4)
	cidrs_safe(r.sources.ipv6)
	r.sources.prefix_lists.state == "absent"
	valid_source(r.sources)
} else := priority({state |
	some state in uncertainty_order
	source_state(r.sources, state)
})

rule_value(r) := r.state if r.state != "known"

else := "fail" if {
	ssh_value(r) == "yes"
	world_value(r) == "yes"
} else := "pass" if ssh_value(r) == "no"

else := "pass" if world_value(r) == "no"

else := priority({state |
	some state in [ssh_value(r), world_value(r)]
	state != "yes"
	state != "no"
})

aggregate(p) := p.rules.state if p.rules.state != "known"

else := "fail" if {
	some rule in p.rules.items
	rule_value(rule) == "fail"
} else := "pass" if {
	every rule in p.rules.items { rule_value(rule) == "pass" }
} else := priority({state |
	some rule in p.rules.items
	state := rule_value(rule)
	state != "pass"
	state != "fail"
})

reason(r) := "DATA_SOURCE_SKIPPED" if r.mode == "data"

else := "DELETED_RESOURCE_SKIPPED" if r.action_category == "delete"

else := "RESOURCE_NOT_SUPPORTED" if r.provider_name != "registry.terraform.io/hashicorp/aws"

else := "RESOURCE_NOT_SUPPORTED" if {
	r.resource_type != "aws_security_group"
	r.resource_type != "aws_security_group_rule"
	r.resource_type != "aws_vpc_security_group_ingress_rule"
} else := "SSH_EGRESS_SKIPPED" if {
	r.ssh_state.representation == "legacy"
	r.ssh_state.direction.value == "egress"
} else := rule_codes[r.ssh_state.direction.state] if {
	r.ssh_state.direction.state != "known"
} else := inline_codes[aggregate(r.ssh_state)] if {
	r.ssh_state.representation == "inline"
} else := rule_codes[aggregate(r.ssh_state)]

inline_codes := {
	"pass": "SSH_INLINE_NO_UNRESTRICTED_INGRESS",
	"fail": "SSH_INLINE_UNRESTRICTED_INGRESS",
	"sensitive": "SSH_INLINE_SENSITIVE",
	"unknown": "SSH_INLINE_UNKNOWN",
	"unverified": "SSH_INLINE_UNVERIFIED",
	"unavailable": "SSH_INLINE_UNAVAILABLE",
	"missing": "SSH_INLINE_MISSING",
	"null": "SSH_INLINE_NULL",
	"invalid_type": "SSH_INLINE_INVALID_TYPE",
	"prefix_list_unresolved": "SSH_INLINE_PREFIX_LIST_UNRESOLVED",
}

rule_codes := {
	"pass": "SSH_RULE_NO_UNRESTRICTED_INGRESS",
	"fail": "SSH_RULE_UNRESTRICTED_INGRESS",
	"sensitive": "SSH_RULE_SENSITIVE",
	"unknown": "SSH_RULE_UNKNOWN",
	"unverified": "SSH_RULE_UNVERIFIED",
	"unavailable": "SSH_RULE_UNAVAILABLE",
	"missing": "SSH_RULE_MISSING",
	"null": "SSH_RULE_NULL",
	"invalid_type": "SSH_RULE_INVALID_TYPE",
	"prefix_list_unresolved": "SSH_RULE_PREFIX_LIST_UNRESOLVED",
}
