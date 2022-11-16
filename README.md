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
2. Install fybrik from the instructions in: (https://fybrik.io/v1.0/get-started/quickstart/)
3. Start the IBM FHIR server service (out-of-box version):   
helm install ibmfhir oci://ghcr.io/elsalant/ibmfhir_orig --version=0.2.0 -n fybrik-system  
(If running in testing mode outside of k8s then:
docker run -p 9443:9443 -e BOOTSTRAP_DB=true ibmcom/ibm-fhir-server )
4. Start the Kafka server:  
   - helm install kafka bitnami/kafka -n fybrik-system  
   - Note that if the Kafka server needs to be exposed externally to the k8s cluster then instead do the following:  
helm install kafka bitnami/kafka --set externalAccess.enabled=true --set externalAccess.autoDiscovery.enabled=true --set externalAccess.service.type=NodePort --set rbac.create=true
 
Then, expose port 9094 on the Kubernetes cluster with the command:
kubectl port-forward service/kafka-0-external  9094:9094  
5. Create namespaces for the different assets: 
kubectl create namespace rest-fhir  
kubectl create namespace rest-blockchain
NOTE:  blockchain requests will only be applied on resources from the rest-blockchain namespace!
6. Pull the files:  
git pull https://github.com/fybrik/REST-read-example.git  
7. Install the policy:  
cd \<INSTALLATION ROOT>
scripts/applyPolicy.sh  
8. Apply the FHIR server secrets and permissions  
scripts/deployPermissions.sh  
9. kubectl apply -f asset.yaml  
10. Apply the module  
kubectl apply -f restFHIRmodule.yaml  
11. Apply the application - note that the name (or JWT) for the requester is in the label.requestedBy field!  
kubectl apply -f restFHIRapplication.yaml  
12. Test  
- a) Load the FHIR server  
kubectl port-forward svc/ibmfhir -n fybrik-system 9443:9443  
scripts/createConsent.sh
scripts/createObservation.sh

- b) Port-forward pod in fybrik-blueprints  
 kubectl get pods -n fybrik-blueprints  
eg: kubectl port-forward pod/\<POD ID> -n fybrik-blueprints 5559:5559  

  c) scripts/curlRequest.sh

### Deprecated testing
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
