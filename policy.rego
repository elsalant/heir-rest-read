package dataapi.authz

rule[{"action": {"name":"RedactColumn", "columns": column_names, "intent": input.context.intent}, "policy": description}] {
  description := "Redact columns tagged as PII in datasets tagged with healthcare = true"
  input.resource.metadata.tags.healthcare
  column_names := [input.resource.metadata.columns[i].name | input.resource.metadata.columns[i].tags.PII]
  count(column_names) > 0
}
rule[{"action": {"name":"Statistics", "columns": column_names}, "policy": description}] {
  description := "Return statistical analysis of glucose in body volume"
  input.resource.metadata.tags.healthcare
  column_names := [input.resource.metadata.columns[i].name | input.resource.metadata.columns[i].tags.stats]
  count(column_names) > 0
}

rule[{"action": {"name":"BlockResource", "columns": column_names}, "policy": description}] {
  description := "Blocks whole resource"
  input.resource.metadata.tags.healthcare
  column_names := [input.resource.metadata.columns[i].name | input.resource.metadata.columns[i].tags.blocked]
  count(column_names) > 0
}

rule[{"name": "Perform a JOIN with the Consent resource", "action": "JoinResource", "joinTable" : "Consent",
"whereclause" : " WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP'", "joinStatement" : " JOIN consent ON observation.subject_reference = consent.patient_reference "}]  {
    1 == 1
}
