# Prospective TAG decisions; only synthetic states/configuration, never values.
package cloud_governance_tags_test

import data.cloud_governance_tags
import rego.v1

cfg := {"tag_configuration": {"required_tag_keys": ["Environment", "Owner", "Project"]}}
base := {"mode": "managed", "action_category": "create", "provider_name": "registry.terraform.io/hashicorp/aws", "resource_type": "aws_instance"}

check(p) := result if {
	result := cloud_governance_tags.decision(object.union(base, {"tag_state": p})) with input as cfg
}

map_for(states, source) := {"source": source, "state": "known", "entries": [
	{"key": "Environment", "state": states[0]}, {"key": "Owner", "state": states[1]}, {"key": "Project", "state": states[2]},
]}

test_all_known_passes if {
	every source in ["tags_all", "tags"] {
		check(map_for(["nonempty", "nonempty", "nonempty"], source)).path == [source]
	}
	check(map_for(["nonempty", "nonempty", "nonempty"], "tags_all")).code == "TAG_ALL_COMPLIANT"
}

test_failure_beats_uncertainty_and_chooses_first_key if {
	result := check(map_for(["blank", "missing", "sensitive"], "tags_all"))
	result.code == "TAG_ALL_KEY_EMPTY"
	result.path == ["tags_all", "Environment"]
}

test_missing_and_null_are_violations if {
	check(map_for(["nonempty", "missing", "unknown"], "tags_all")).code == "TAG_ALL_KEY_MISSING"
	check(map_for(["nonempty", "null", "unknown"], "tags")).code == "TAG_RESOURCE_KEY_EMPTY"
}

test_uncertainty_priority_is_deterministic if {
	check(map_for(["unknown", "invalid_type", "sensitive"], "tags_all")).path == ["tags_all", "Project"]
	check(map_for(["unknown", "unknown", "invalid_type"], "tags_all")).path == ["tags_all", "Environment"]
	check(map_for(["nonempty", "nonempty", "invalid_type"], "tags")).code == "TAG_RESOURCE_KEY_INVALID_TYPE"
}

test_absence_and_null_maps_fail if {
	check({"source": "tags", "state": "missing"}).code == "TAG_RESOURCE_MAP_MISSING"
	check({"source": "tags_all", "state": "null"}).code == "TAG_ALL_MAP_NULL"
}

test_withheld_maps_and_roots_are_indeterminate_reasons if {
	every source in ["tags", "tags_all"] {
		every state in ["unknown", "sensitive", "invalid_type"] {
			check({"source": source, "state": state}).path == [source]
		}
	}
	check({"source": "unresolved", "state": "unverified"}).code == "TAG_UNVERIFIED"
	check({"source": "unresolved", "state": "unavailable"}).code == "TAG_UNAVAILABLE"
}

test_exclusions_need_no_projection if {
	cloud_governance_tags.decision(object.union(base, {"mode": "data"})).code == "DATA_SOURCE_SKIPPED"
	cloud_governance_tags.decision(object.union(base, {"action_category": "delete"})).code == "DELETED_RESOURCE_SKIPPED"
	cloud_governance_tags.decision(object.union(base, {"resource_type": "aws_rds_cluster_instance"})).code == "RESOURCE_NOT_SUPPORTED"
}

test_empty_config_and_entries_cannot_pass if {
	not cloud_governance_tags.decision(object.union(base, {"tag_state": map_for(["nonempty", "nonempty", "nonempty"], "tags_all")})) with input as {"tag_configuration": {"required_tag_keys": []}}
	not check({"source": "tags_all", "state": "known", "entries": []})
}
