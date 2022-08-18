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

rule[{"name": "Block records if no consent given", "action": "FilterPred", "token" : "organization", "filterPredicate" :
"WHERE organisation.label = '**T1**'", "replaceMe": "**T1**"}]  {
    input.request.asset.name == "videos"
    not contains(input.request.role, "Admin")
    not contains(input.request.role, "Manager")
