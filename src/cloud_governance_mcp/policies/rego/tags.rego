# Required tags use value-free states and stable operator-key order.
package cloud_governance_tags

import rego.v1

codes := {
	"tags_all": {
		"compliant": "TAG_ALL_COMPLIANT",
		"null": "TAG_ALL_MAP_NULL",
		"sensitive": "TAG_ALL_MAP_SENSITIVE",
		"unknown": "TAG_ALL_MAP_UNKNOWN",
		"invalid_type": "TAG_ALL_MAP_INVALID_TYPE",
		"key_missing": "TAG_ALL_KEY_MISSING",
		"key_empty": "TAG_ALL_KEY_EMPTY",
		"key_sensitive": "TAG_ALL_KEY_SENSITIVE",
		"key_unknown": "TAG_ALL_KEY_UNKNOWN",
		"key_invalid_type": "TAG_ALL_KEY_INVALID_TYPE",
	},
	"tags": {
		"compliant": "TAG_RESOURCE_COMPLIANT",
		"missing": "TAG_RESOURCE_MAP_MISSING",
		"null": "TAG_RESOURCE_MAP_NULL",
		"sensitive": "TAG_RESOURCE_MAP_SENSITIVE",
		"unknown": "TAG_RESOURCE_MAP_UNKNOWN",
		"invalid_type": "TAG_RESOURCE_MAP_INVALID_TYPE",
		"key_missing": "TAG_RESOURCE_KEY_MISSING",
		"key_empty": "TAG_RESOURCE_KEY_EMPTY",
		"key_sensitive": "TAG_RESOURCE_KEY_SENSITIVE",
		"key_unknown": "TAG_RESOURCE_KEY_UNKNOWN",
		"key_invalid_type": "TAG_RESOURCE_KEY_INVALID_TYPE",
	},
}

root_codes := {"sensitive": "TAG_SENSITIVE", "unknown": "TAG_UNKNOWN", "unverified": "TAG_UNVERIFIED", "unavailable": "TAG_UNAVAILABLE"}

# Array comprehensions preserve the validated configuration order. Choosing the
# first witness avoids a quadratic scan comparing every pair of required keys.
known(p) := {"code": codes[p.source].key_missing, "path": [p.source, failures[0].key]} if {
	failures := [entry | some entry in p.entries; failure_state(entry.state)]
	failures[0].state == "missing"
} else := {"code": codes[p.source].key_empty, "path": [p.source, failures[0].key]} if {
	failures := [entry | some entry in p.entries; failure_state(entry.state)]
	empty_state(failures[0].state)
} else := {"code": codes[p.source].key_sensitive, "path": [p.source, entries[0].key]} if {
	entries := [entry | some entry in p.entries; entry.state == "sensitive"]
	entries[0].key != ""
} else := {"code": codes[p.source].key_unknown, "path": [p.source, entries[0].key]} if {
	entries := [entry | some entry in p.entries; entry.state == "unknown"]
	entries[0].key != ""
} else := {"code": codes[p.source].key_invalid_type, "path": [p.source, entries[0].key]} if {
	entries := [entry | some entry in p.entries; entry.state == "invalid_type"]
	entries[0].key != ""
} else := {"code": codes[p.source].compliant, "path": [p.source]} if {
	p.entries[0].key != ""
	every entry in p.entries { entry.state == "nonempty" }
}

observed(p) := {"code": root_codes[p.state], "path": []} if p.source == "unresolved"

else := {"code": codes[p.source][p.state], "path": [p.source]} if {
	p.source != "unresolved"
	p.state != "known"
} else := known(p) if p.state == "known"

decision(r) := {"code": "DATA_SOURCE_SKIPPED", "path": []} if r.mode == "data"

else := {"code": "DELETED_RESOURCE_SKIPPED", "path": []} if r.action_category == "delete"

else := {"code": "RESOURCE_NOT_SUPPORTED", "path": []} if r.provider_name != "registry.terraform.io/hashicorp/aws"

else := {"code": "RESOURCE_NOT_SUPPORTED", "path": []} if {
	not supported(r.resource_type)
} else := observed(r.tag_state) if {
	input.tag_configuration.required_tag_keys[0] != ""
}

failure_state(s) if s == "missing"
failure_state(s) if empty_state(s)
empty_state(s) if s == "blank"
empty_state(s) if s == "null"
supported(t) if t == "aws_instance"
supported(t) if t == "aws_security_group"
supported(t) if t == "aws_db_instance"
supported(t) if t == "aws_rds_cluster"
supported(t) if t == "aws_s3_bucket"
