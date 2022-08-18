### This is an example of Fybrik read module that uses REST protocol to connect to a FHIR server to obtain medical records.  Policies redact the information returned by the FHIR server or can even restrict access to a given resource type.
### User authentication is enabled, as well as (optional) logging to Kafka

### Concepts
1. The FHIR server itself is the Fybrik data source and described by a Fybrik Asset.
2. The "columns" in the asset.yaml represent the schema for a FHIR resource.   The name of the column can either an
attribute which will be applied to all FHIR resources (e.g. "id"), or this can be made more specific by specifying
the name in the format <resource>.<attribute>, e.g. Patient.id.
3. The code will attempt to connect to a Kafka server and topic.  (Default values can be override by using the 
HEIR_KAFKA_TOPIC and HEIR_KAFKA_HOST environment variables).  If the initial connection to Kafka fails, the code 
will not attempt to log to Kafka. 
4. Supports row-level filtering of data.  The policy passes back the SQL 
"WHERE" clause that will be evaluated on each returned record.

Do once:  make sure helm v3.7+ is installed
> helm version

1. export HELM_EXPERIMENTAL_OCI=1
2. Install fybrik from the instructions in: https://fybrik.io/v0.6/get-started/quickstart/
3. Start the IBM FHIR server service (out-of-box version):   
helm install ibmfhir oci://ghcr.io/elsalant/ibmfhir_orig --version=0.2.0 -n fybrik-system
4. Start the Kafka server:  
   - helm install kafka bitnami/kafka -n fybrik-system  
   - Note that if the Kafka server needs to be exposed externally to the k8s cluster then instead do the following:
helm install kafka bitnami/kafka --set externalAccess.enabled=true --set externalAccess.autoDiscovery.enabled=true --set externalAccess.service.type=NodePort --set rbac.create=true
 
Then, expose port 9094 on the Kubernetes cluster with the command:
kubectl port-forward service/kafka-0-external  9094:9094  
5. Create a namespace for the demo:  
kubectl create namespace rest-fhir  
6. Pull the files:  
git pull https://github.com/fybrik/REST-read-example.git  
7. Install the policy:  
\<ROOT>/scripts/applyPolicy.sh  
8. Apply the FHIR server secrets and permissions  
\<ROOT>/scripts/deployPermissions.sh  
9. kubectl apply -f \<ROOT>/asset.yaml  
10. Apply the module  
kubectl apply -f \<ROOT>/restFHIRmodule.yaml  
11. Apply the application - note that the name (or JWT) for the requester is in the label.requestedBy field!  
kubectl apply -f \<ROOT>/restFHIRapplication.yaml  
12. Test  
- a) Load database  
kubectl port-forward svc/ibmfhir -n fybrik-system 9443:9443  
\<ROOT>/scripts/createPatient.sh  
- b) Port-forward pod in fybrik-blueprints  
 kubectl get pods -n fybrik-blueprints  
eg: kubectl port-forward pod/\<POD ID> -n fybrik-blueprints 5559:5559  
- c) curl -X GET -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJIRUlSIHRlc3QiLCJpYXQiOjE2NDM2MTQ3NzQsImV4cCI6MTczODMwOTIwNCwiYXVkIjoiTk9LTFVTIiwic3ViIjoiaGVpci13cDItdGVzdCIsIkdpdmVuTmFtZSI6IkVsaW90IiwiU3VybmFtZSI6IlNhbGFudCIsIkVtYWlsIjoic2FsYW50QGlsLmlibS5jb20iLCJSb2xlIjpbIk1hbmFnZXIiLCJQcm9qZWN0IEFkbWluaXN0cmF0b3IiXX0.WxBSdu7xe9LIsu_MlzX3spmvQmQpRm8MFK0d19eW_no" http://localhost:5559/Patient
- To load Observations:  
  docker run --network host ghcr.io/elsalant/observation-generator:v1  
(NOTE: On MacOS, the "--network" switch may not work.  In that case, it might be easiest to port-forward the fhir server and 
then run observationGenerator.py from a local Python environment
e.g.  
  a) kubectl port-forward svc/ibmfhir -n fybrik-system 9443:9443 
  b) python3 observationGenerator.py (under heir-FHIR/python/observationGenerator.py) 

#### Hints
To test redaction: pick a field in the resource (e.g. "id") and set the tag in the asset.yaml file to "PII".
Note that to redact a given field in a given resource, e.g. "id" in "Patient" sources, in the asset.yaml file, specify the componentsMetadata value as "Patient.id".

If either the asset or policy is changed, then the Fybrik application needs to be restarted:
kubectl delete -f <name of FybrikApplication file>  
kubectl apply -f <name of FybrikApplication file> 
 
#### DEVELOPMENT

1. To build Docker image:  
make docker-build  

Push the image to Docker package repo  
make docker-push

2. Package and push the Helm chart to the repo 
export HELM_EXPERIMENTAL_OCI=1  
make helm-package 
make helm-push
