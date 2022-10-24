package dataapi.authz

rule[{"action": {"name": "JoinAndRedact", "joinTable" : "Consent", "whereclause" : " WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP", "joinStatement" : " JOIN consent ON observation.subject_reference = consent.patient_reference "}, "policy": description}]  {
    description := "Executes a JOIN on the Consent table"
    1 == 1
}