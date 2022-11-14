package dataapi.authz

rule[{"action": {"name": "JoinAndRedact", "joinTable" : "Consent", "whereclause" : " WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP", "joinStatement" : " JOIN consent ON observation.subject_reference = consent.patient_reference ", "columns": column_names}, "policy": description}]  {
    description := "Executes a JOIN on the Consent table"
    column_names := [input.resource.metadata.columns[i].name | input.resource.metadata.columns[i].tags.PII]
    count(column_names) > 0
}

rule[{"action": {"name": "RedactColumn",  "columns": column_names, "noredact": "admin"}, "policy": description}]  {
    description := "RedactColumns for blockchain"
    input.resource.metadata.tags.blockchain
    column_names := [input.resource.metadata.columns[i].name | input.resource.metadata.columns[i].tags.PII]
    count(column_names) > 0
}