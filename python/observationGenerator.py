import requests
import curlify
import datetime
import json
import random
import sys
import os
import re
import urllib

observation = '{ \
  "resourceType": "Observation", \
  "id": "f001", \
  "text": { \
    "status": "generated", \
    "div": "<div xmlns=\\"http://www.w3.org/1999/xhtml\\"><p><b>Generated Narrative with Details</b></p><p><b>id</b>: f001</p><p><b>identifier</b>: 6323 (OFFICIAL)</p><p><b>status</b>: final</p><p><b>code</b>: Glucose [Moles/volume] in Blood <span>(Details : {LOINC code \'15074-8\' = \'Glucose [Moles/volume] in Blood\', given as \'Glucose [Moles/volume] in Blood\'})</span></p><p><b>subject</b>: <a>P. van de Heuvel</a></p><p><b>effective</b>: 02/04/2013 9:30:10 AM - 03/04/2013 3:30:10 PM</p><p><b>performer</b>: <a>A. Langeveld</a></p><p><b>value</b>: 6.3 mmol/l<span> (Details: UCUM code mmol/L = \'mmol/L\')</span></p><p><b>interpretation</b>: High <span>(Details : {http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation code \'H\' = \'High\', given as \'High\'})</span></p><h3>ReferenceRanges</h3><table><tr><td>-</td><td><b>Low</b></td><td><b>High</b></td></tr><tr><td>*</td><td>3.1 mmol/l<span> (Details: UCUM code mmol/L = \'mmol/L\')</span></td><td>6.2 mmol/l<span> (Details: UCUM code mmol/L = \'mmol/L\')</span></td></tr></table></div>" \
  }, \
  "identifier": [ \
    { \
      "use": "official", \
      "system": "http://www.bmc.nl/zorgportal/identifiers/observations", \
      "value": "6323" \
    } \
  ], \
  "status": "final", \
  "code": { \
    "coding": [ \
      { \
        "system": "http://loinc.org", \
        "code": "14745-4", \
        "display": "Glucose [Moles/volume] in Body Fluid" \
      } \
    ] \
  }, \
  "subject": { \
    "reference": "Patient/f001", \
    "display": "P. van de Heuvel" \
  }, \
  "effectivePeriod": { \
    "start": "2020-11-11T09:30:10+01:00" \
  }, \
    "issued": "2020-11-11T15:30:10+01:00", \
  "performer": [ \
    { \
      "reference": "Practitioner/f005", \
      "display": "A. Langeveld" \
    }  \
  ],  \
  "valueQuantity": {  \
    "value": 6.3,  \
    "unit": "mmol/l",  \
    "system": "http://unitsofmeasure.org",  \
    "code": "mmol/L"  \
  }, \
  "interpretation": [ \
    { \
      "coding": [ \
        { \
          "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", \
          "code": "H", \
          "display": "High" \
        } \
      ] \
    } \
  ], \
  "referenceRange": [ \
    { \
      "low": { \
        "value": 3.1, \
        "unit": "mmol/l", \
        "system": "http://unitsofmeasure.org", \
        "code": "mmol/L" \
      }, \
      "high": { \
        "value": 6.2,  \
        "unit": "mmol/l",  \
        "system": "http://unitsofmeasure.org",  \
        "code": "mmol/L"  \
      }  \
    }  \
  ]  \
}'

GLUCOSE_LOW = 2.6
GLUCOSE_HIGH = 8.1

DEFAULT_FHIR_USER = 'fhiruser'
DEFAULT_FHIR_PW = 'change-password'
DEFAULT_FHIR_HOST = 'https://127.0.0.1:9443'

OBSERVATION_ENDPOINT = '/fhir-server/api/v4/Observation'

def main(reps=10):
    if len(sys.argv[1:]):
        reps=sys.argv[1:][0]

    start_date = datetime.date(2020,1,1)

    observationDict = json.loads(observation)
    fhir_host = os.getenv("HEIR_FHIR_HOST") if os.getenv("HEIR_FHIR_HOST") else DEFAULT_FHIR_HOST
    fhir_user = os.getenv("HEIR_FHIR_USER") if os.getenv("HEIR_FHIR_USER") else DEFAULT_FHIR_USER
    fhir_pw = os.getenv("HEIR_FHIR_PW") if os.getenv("HEIR_FHIR_PW") else DEFAULT_FHIR_PW
    auth = (fhir_user, fhir_pw)

    for x in range(reps):
        randomGlucose = random.randint(GLUCOSE_LOW*10,GLUCOSE_HIGH*10)/10
        randomDateOffset = random.randint(0,365)
        random_observation_date = start_date + datetime.timedelta(days=randomDateOffset)

        patientIdList = ['Patient/f001', 'Patient/g002', 'Patient/h003','Patient/i004']

        patientId = patientIdList[random.randint(0,3)]
        tString = random_observation_date.strftime("%Y-%m-%d")+'T09:30:10+01:00'
        #print('glucose level = {:1f}, patientID = {:s}, observationDate = {:s}'.format(randomGlucose, patientId, tString))
        observationDict['valueQuantity']['value'] = randomGlucose
        observationDict['effectivePeriod']['start'] = tString
 #       observationDict['effectivePeriod']['issued'] = tString
        observationDict['subject']['reference'] = patientId
        observationStr = json.dumps(observationDict)
        print(observationStr)

        queryStringsLessBlanks = re.sub(' +', ' ', observationStr)
        urlString = fhir_host + OBSERVATION_ENDPOINT
        print("urlString = " + urlString)
    #    curlString = urllib.parse.unquote_plus(queryStringsLessBlanks)

        try:
            r = requests.post(urlString, auth=auth, data=queryStringsLessBlanks, headers={'Content-Type': 'application/json'}, verify=False)
        except Exception as e:
            print("Exception in handleQuery, queryString = " + queryStringsLessBlanks + ", auth = " + str(auth))
            print(e.args)
        print("curl request = " + curlify.to_curl(r.request))

if __name__ == "__main__":
    print("Generating 30 records")
    main(30)