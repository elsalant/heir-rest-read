curl -k --location --request POST 'https://localhost:9443/fhir-server/api/v4/Consent' --header 'Content-Type: application/fhir+json' \
--user "fhiruser:change-password" --data-binary  "@testConsent.json"
curl -k --location --request POST 'https://localhost:9443/fhir-server/api/v4/Consent' --header 'Content-Type: application/fhir+json' \
--user "fhiruser:change-password" --data-binary  "@testConsent1.json"
