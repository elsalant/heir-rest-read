kubectl -n fybrik-system create configmap fhir-read-policy --from-file=policy.rego
kubectl -n fybrik-system label configmap fhir-read-policy openpolicyagent.org/policy=rego
while [[ $(kubectl get cm fhir-read-policy -n fybrik-system -o 'jsonpath={.metadata.annotations.openpolicyagent\.org/policy-status}') != '{"status":"ok"}' ]]; do echo "waiting for policy to be applied" && sleep 5; done
