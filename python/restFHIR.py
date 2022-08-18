#
# Copyright 2022 IBM Corp.
# SPDX-License-Identifier: Apache-2.0
#

from flask import Flask, request
from kubernetes import client, config
from kafka import KafkaProducer
import requests
import yaml
import urllib.parse as urlparse
import curlify
import urllib.parse
import json
import jwt
from json import loads
import time
from datetime import date, datetime, timedelta, timezone
import pandas as pd
import os
import re
import base64

FLASK_PORT_NUM = 5559  # this application

ACCESS_DENIED_CODE = 403
ERROR_CODE = 406
BLOCK_CODE = 501
VALID_RETURN = 200

TEST = False   # allows testing outside of Fybrik/Kubernetes environment

if TEST:
    DEFAULT_FHIR_HOST = 'https://localhost:9443/fhir-server/api/v4/'
else:
    DEFAULT_FHIR_HOST = 'https://ibmfhir.fybrik-system:9443/fhir-server/api/v4/'
DEFAULT_FHIR_USER = 'fhiruser'
DEFAULT_FHIR_PW = 'change-password'

DEFAULT_KAFKA_TOPIC = 'fhir-wp2-logging'
DEFAULT_KAKFA_HOST = 'kafka.fybrik-system:9092'

kafka_host = os.getenv("HEIR_KAFKA_HOST") if os.getenv("HEIR_KAFKA_HOST") else DEFAULT_KAKFA_HOST
kafka_topic = os.getenv("HEIR_KAFKA_TOPIC") if os.getenv("HEIR_KAFKA_TOPIC") else DEFAULT_KAFKA_TOPIC

FIXED_SCHEMA_ROLE = 'Role'
FIXED_SCHEMA_ORG = 'aud'  # Use the audience role?

DEFAULT_TIMEWINDOW = 3560  # days - should be 14
HIGH_THRESHOLD_DEFAULT = 8.3
LOW_THRESHOLD_DEFAULT = 4

fhir_host = os.getenv("HEIR_FHIR_HOST") if os.getenv("HEIR_FHIR_HOST") else DEFAULT_FHIR_HOST
fhir_user = os.getenv("HEIR_FHIR_USER") if os.getenv("HEIR_FHIR_USER") else DEFAULT_FHIR_USER
fhir_pw = os.getenv("HEIR_FHIR_PW") if os.getenv("HEIR_FHIR_PW") else DEFAULT_FHIR_PW
time_window = os.getenv("HEIR_TIMEWINDOW") if os.getenv("HEIR_TIMEWINDOW") else DEFAULT_TIMEWINDOW

app = Flask(__name__)
cmDict = {}

def handleQuery(queryGatewayURL, queryString, auth, params, method):
  #  print("querystring = " + queryString)
    queryStringsLessBlanks = re.sub(' +', ' ', queryString)

    curlString = queryGatewayURL + urllib.parse.unquote_plus(queryStringsLessBlanks)
 #   curlString = queryGatewayURL + str(base64.b64encode(queryStringsLessBlanks.encode('utf-8')))
    print("curlCommands: curlString = ", curlString)
    try:
      if (method == 'POST'):
        r = requests.post(curlString, auth=auth, params=params, verify=False)
      else:
        r = requests.get(curlString, auth=auth, params=params, verify=False)
    except Exception as e:
      print("Exception in handleQuery, curlString = " + curlString + ", auth = " + str(auth))
      print(e.args)
      return(ERROR_CODE)

    print("curl request = " + curlify.to_curl(r.request))
 #   if r.status_code != 200:
 #       return None
    if (r.status_code == 404):
      print("handleQuery: empty return!")
      return(None)
    else:
      try:
        returnList = r.json()  # decodes the response in json
      except:
        print('curlCommands: curl return is not in JSON format! Returing as binary')
        returnList = r.content
#    if re.response is None:
#        print("---> error on empty returnList in curlCommands.py")
#    else:
 #       print('[%s]' % ', '.join(map(str, returnList)))

    return (returnList)

def checkRequester():
    if TEST:
        requester = 'EliotSalant'
    else:
        requester = cmDict['SUBMITTER']
    print("SUBMITTER = " + requester)
    return(requester)

def decryptJWT(encryptedToken, flatKey):
# String with "Bearer <token>".  Strip out "Bearer"...
    prefix = 'Bearer'
    assert encryptedToken.startswith(prefix), '\"Bearer\" not found in token' + encryptedToken
    strippedToken = encryptedToken[len(prefix):].strip()
    decodedJWT = jwt.api_jwt.decode(strippedToken, options={"verify_signature": False})
    print('decodedJWT = ', decodedJWT)
# We might have an nested key in JWT (dict within dict).  In that case, flatKey will express the hierarchy and so we
# will interatively chunk through it.
    decodedKey = None
    while type(decodedJWT) is dict:
        for s in flatKey.split('.'):
            if s in decodedJWT:
                decodedJWT = decodedJWT[s]
                decodedKey = decodedJWT
            else:
                print("warning: " + s + " not found in decodedKey!")
                return decodedKey
    return decodedKey

def getSecretKeysExample(secret_name, secret_namespace):  # Not needed here.  Maybe in JWT is pushed into a secret key?
    try:
        config.load_incluster_config()  # in cluster
    except:
        config.load_kube_config()   # useful for testing outside of k8s
    v1 = client.CoreV1Api()
    secret = v1.read_namespaced_secret(secret_name, secret_namespace)
    accessKeyID = base64.b64decode(secret.data['access_key'])
    secretAccessKey = base64.b64decode(secret.data['secret_key'])
    return(accessKeyID.decode('ascii'), secretAccessKey.decode('ascii'))

def read_from_fhir(queryString):
    if TEST:
        fhiruser = fhir_user
        fhirpw = fhir_pw
    else:
        fhiruser, fhirpw = getSecretKeys()
    queryURL = fhir_host
    params = ''
 #   auth = (fhir_user, fhir_pw)
    auth = (fhiruser, fhirpw)

    returnedRecord = handleQuery(queryURL, queryString, auth, params, 'GET')
    if returnedRecord == None:
        return(['{"ERROR" : "returnedRecord empty!"}'], ERROR_CODE)
    # Strip the bundle information out and convert to data frame
    recordList = []
    try:
        for record in returnedRecord['entry']:
            print("bundle detected")
            recordList.append(json.dumps(record['resource']))
    except:
        print("no information returned!")
        return(['{"ERROR" : "No information returned!"}'], ERROR_CODE)
#    jsonList = [ast.literal_eval(x) for x in recordList]
    jsonList = [json.loads(x) for x in recordList]
    return (jsonList, VALID_RETURN)

def getSecretKeys():
    try:
        config.load_incluster_config()  # in cluster
    except:
        config.load_kube_config()   # useful for testing outside of k8s
    v1 = client.CoreV1Api()
    secret_namespace = cmDict['SECRET_NSPACE']
    secret_fname = cmDict['SECRET_FNAME']
    print("secret_fname = " + secret_fname + " secret_namespace = " + secret_namespace)
    secret = v1.read_namespaced_secret(secret_fname, secret_namespace)
    fhiruser = base64.b64decode(secret.data['fhiruser'])
    fhirpw = base64.b64decode(secret.data['fhirpasswd'])
    print('getSecretKeys: fhiruser = ' + fhiruser.decode('ascii') + ' fhirpw = ' + fhirpw.decode('ascii'))
    return(fhiruser.decode('ascii'), fhirpw.decode('ascii'))

def connect_to_kafka():
    global kafkaDisabled
    try:
        producer = KafkaProducer(
            bootstrap_servers=[kafka_host],
            request_timeout_ms=2000
        )  # , value_serializer=lambda x:json.dumps(x).encode('utf-8'))
    except Exception as e:
        print("\n--->WARNING: Connection to Kafka failed.  Is the server on " + kafka_host + " running?")
        print(e)
        kafkaDisabled = True
        return None
    kafkaDisabled = False
    print("Connection to Kafka succeeded! " + kafka_host)
    return(producer)

def apply_policy(jsonList, policies):
    df = pd.json_normalize(jsonList)
    redactedData = []
    # Redact df based on policy returned from the policy manager
    meanStr = ''
    stdStr = ''  # standard deviation
    std = ''
   # cleanPatientId = df['subject.reference'][0].replace('/', '-')
    print('inside apply_policy. Length policies = ', str(len(policies)), " type(policies) = ", str(type(policies)))
#    for policy in policies:
    policy = policies
    print('policy = ', str(policy))
    if policy['transformations'][0] == None:
        print('No transformations found!')
        return (str(df.to_json()))
    action = policy['transformations'][0]['action']
    if action == '':
        return (str(df.to_json()), VALID_RETURN)
    print('Action = ' + action)

# Allow specifying a particular attribute for a given resource by specifying the in policy file the
# the column name as <resource>.<column_name>
    dfToRows = []
    if action == 'DeleteColumn':
        try:
            for col in policy['transformations'][0]['columns']:
                if '.' in col:
                    (resource, col) = col.split('.')
                    print("resource, attribute specified: " + resource + ", " + col)
                    if (df['resourceType'][0]) != resource:
                        continue
                df.drop(col, inplace=True, axis=1)
        except:
            print("No such column " + col + " to delete")
        for i in df.index:
  #        dfToRows = dfToRows + df.loc[i].to_json()
            jsonList = [json.loads(x) for x in dfToRows]
        return (jsonList, VALID_RETURN)
 #       redactedData.append(dfToRows)
 #       return(str(redactedData))

    if action == 'RedactColumn':
        replacementStr = policy['transformations'][0]['options']['redactValue']
        for col in policy['transformations'][0]['columns']:
            if '.' in col:
# We can either be passing something of the form:  resource.attribute, or attribute, where attribute
# itself may contain a '.'.  Take the result of the first split and see if that is equal to resourceType to differentiate
                (resourceCandidate, colCandidate) = col.split('.',1)
                if resourceCandidate == df['resourceType'][0]:
                    col = colCandidate
                print("resource, attribute specified: " + resourceCandidate + ", " + col)
            try:
    # Replace won't replace floats or ints.  Instead, convert to column to be replaced to a string
    # before replacing
  #              df[col].replace(r'.+', replacementStr, regex=True, inplace=True)
                df[col]= df[col].astype(str).str.replace(r'.+', replacementStr, regex=True)
            except:
                print("No such column " + col + " to redact")
        for i in df.index:
 #           dfToRows = dfToRows + df.loc[i].to_json()
            dfToRows.append(df.loc[i].to_json())
        jsonList = [json.loads(x) for x in dfToRows]
        return (jsonList, VALID_RETURN)
    #    redactedData.append(dfToRows)
    #    return(str(redactedData))

    if action == 'BlockResource':
    #    if policy['transformations'][0]['columns'][0] == df['resourceType'][0]:
        if df['resourceType'][0] in policy['transformations'][0]['columns']:
            return('{"result": "Resource blocked by policy!!"}', BLOCK_CODE)
        else:
            print('No resource to block!. resourceType =  ' + df['resourceType'][0] + \
                  ' policy[\'transformations\'][0][\'columns\'][0] = ' + df['resourceType'][0] in policy['transformations'][0]['columns'][0])
            return(str(df.to_json()), VALID_RETURN)

    if action == 'Statistics':
        for col in policy['transformations'][0]['columns']:
            print('col = ', col)
            try:
                std = df[col].std()
            except:
                print('No col ' + col + ' found!')
                print(df.keys())
            stdStr = '{\"CGM_STD\": \"' + str(std) + '\"}'
            mean = df[col].mean()
            meanStr = '{\"CGM_MEAN\": \"' + str(mean) + '\"}'
        redactedData.append(meanStr+ ' ' + stdStr)
# Calculate Time in Range, Time Above Range, Time Below Range
        numObservations = len(df)
        try:
            high_threshold = df['referenceRange'][0][0]['high']['value']
            print('high_threshold found in resource as ' + str(high_threshold))
        except:
            high_threshold = HIGH_THRESHOLD_DEFAULT
        try:
            low_threshold = df['referenceRange'][0][0]['low']['value']
            print('low_threshold found in resource as ' + str(low_threshold))
        except:
            low_threshold = LOW_THRESHOLD_DEFAULT
        tar = round((len(df.loc[df[col]>high_threshold,col])/numObservations)*100)
        tbr = round((len(df.loc[df[col]<low_threshold,col])/numObservations)*100)
        tir = 100 - tar - tbr
        d = {
            'PATIENT_ID': df['subject.reference'][0],
            'CGM_TIR': tir,
            'CGM_TAR': tar,
            'CGM_TBR': tbr,
            'CGM_MEAN': mean,
            'CGM_STD': std
        }
        return(str(d), VALID_RETURN)
    return('{"Unknown transformation": "'+ action + '"}', ERROR_CODE)

def timeWindow_filter(df):
    print("keys = ", df.keys())
    # drop rows that are outside of the timeframe
    df.drop(df.loc[(pd.to_datetime(df['effectivePeriod.start'], utc=True) + timedelta(days=time_window) < datetime.now(timezone.utc)) | (df['resourceType'] != 'Observation')].index, inplace=True)
    return df

# @app.route('/query/<queryString>')
# def query(queryString):
# Catch anything
@app.route('/<path:queryString>',methods=['GET', 'POST', 'PUT'])
def getAll(queryString=None):
    global cmDict
    print("queryString = " + queryString)
    print('request.url = ' + request.url)

# Handle authentication in the header
    noJWT = True
    payloadEncrypted = request.headers.get('Authorization')
    organization = None
    role = None
    givenName = 'None'
    surName = 'None'
    if (payloadEncrypted != None):
        noJWT = False
        roleKey = os.getenv("SCHEMA_ROLE") if os.getenv("SCHEMA_ROLE") else FIXED_SCHEMA_ROLE
        organizationKey = os.getenv("SCHEMA_ORG") if os.getenv("SCHEMA_ORG") else FIXED_SCHEMA_ORG
        try:
            role = decryptJWT(payloadEncrypted, roleKey)
        except:
            print("Error: no role in JWT!")
            role = 'ERROR NO ROLE!'
        try:
            givenName = decryptJWT(payloadEncrypted, 'GivenName')
            surName = decryptJWT(payloadEncrypted, 'Surname')
        except:
            print("Error extracting Surname and/or GivenName")
        try:
            organization = decryptJWT(payloadEncrypted, organizationKey)
        except:
            print("No organization JWT")
    if (noJWT):
        print("No JWT passed!")
        role = request.headers.get('role')  # testing only
    if (role == None):
        role = 'ERROR NO ROLE!'
    if (organization == None):
        organization = 'NO ORGANIZATION'
    print('Surname = ' + surName + ' GivenName = ' + givenName + ' role = ', role, " organization = ", organization)
#   Role in JWT needs to match role of requestor from original FybrikApplication deployment
    requester = checkRequester()  # from the FybrikApplication
    timeOut = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Hack for testing without JWT
    queryRequester = role if noJWT else givenName+surName
    assetID = cmDict['assetID']
    intent = 'Not given'
    for i in cmDict['transformations']:
        if 'intent' in i:
            intent = i['intent']
    if (queryRequester != requester):
        print("queryRequester " + queryRequester + " != " + requester)
        jSONout = '{\"Timestamp\" : \"' + timeOut + '\", \"Requester\": \"' + queryRequester + '\", \"Query\": \"' + queryString + \
                    '\", \"ClientIP\": \"' + str(request.remote_addr) + '\",' + \
                  '\"assetID": \"' + assetID + '\",' + \
                  '\"policyDecision\": \"' + str(cmDict['transformations']) + '\",' + \
                    '"intent\": \"' + intent +'\", \"Outcome": \"UNAUTHORIZED\"}'
        logToKafka(jSONout, kafka_topic)
        return ("{\"Error\": \"Unauthorized access attempt!\"}")

    # Go out to the actual FHIR server
    print("request.method = " + request.method)
    dfBack, messageCode = read_from_fhir(queryString)
    if (messageCode != VALID_RETURN):
        return ("{\"Error\": \"No information returned!\"}")
#apply_policies
    ans, messageCode = apply_policy(dfBack, cmDict)
    if messageCode == VALID_RETURN:
        outcome = "AUTHORIZED"
    elif messageCode == BLOCK_CODE:
        outcome = "RESTRICTED"
    else:
        outcome = "ERROR"
    # Log the query request
    jSONout = '{\"Timestamp\" : \"' + timeOut + '\", \"Requester\": \"' + requester + '\", \"Query\": \"' + queryString + '\",' + \
              '\"ClientIP\": \"' + str(request.remote_addr) + '\",' + \
              '\"assetID": \"' + assetID + '\",' + \
              '\"policyDecision\": \"'  + str(cmDict['transformations']) + '\",' + \
              '\"intent\": \"' + intent + '\",\"Outcome": \"' + outcome + '\"}'
    logToKafka(jSONout, kafka_topic)
    return (json.dumps(ans))

def logToKafka(jString, kafka_topic):
    global producer

    if kafkaDisabled:
        print("Kafka topic: " + kafka_topic + " log string: " + jString)
        print("But kafka is disabled...")
        return
    jSONoutBytes = str.encode(jString)
    try:
        print("Writing to Kafka queue " + kafka_topic + ": " + jString)
        producer.send(kafka_topic, value=jSONoutBytes)  # to the SIEM
    except Exception as e:
        print("Write to Kafka failed.  Is the server on " + kafka_topic + " running?")
        print(e)

def main():
    global cmDict
    global kafkaDisabled
    kafkaDisabled = True
    global producer

    print("starting module!!")

    CM_PATH = '/etc/conf/conf.yaml' # from the "volumeMounts" parameter in templates/deployment.yaml

    cmReturn = ''
    producer = connect_to_kafka()

    if not TEST:
        try:
            with open(CM_PATH, 'r') as stream:
                cmReturn = yaml.safe_load(stream)
        except Exception as e:
            print(e.args)
            time.sleep(180)  # on a error, give time to look at the formating in the /etc/conf/config.yaml file
            raise ValueError('Error reading from file! ' + CM_PATH)
        print('cmReturn = ', cmReturn)
    if TEST:
        cmDict = {'dict_item': [
            ('transformations', [{'action': 'BlockResource', 'description': 'redact columns: [valueQuantity.value id]',
            'columns': ['valueQuantity.value', 'id'], 'options': {'redactValue': 'XXXXX'}},
            {'action': 'ReturnIntent', 'description': 'return intent',
            'columns': ['N/A'], 'intent': 'research'}]), ('assetID', 'sql-fhir/observation-json')]}
        cmDict = dict(cmDict['dict_item'])
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redact columns: [valueQuantity.value id]',
   #          'columns': ['valueQuantity.value', 'id'], 'options': {'redactValue': 'XXXXX'}}]), ('assetID', 'sql-fhir/observation-json')]}
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: Patient', 'columns': ['Patient'], 'options': {'redactValue': 'XXXXX'}}])]}
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: ',
   #                                               'columns': ['valueQuantity.value','subject.display', 'text.div', 'subject.reference'],
   #                                               'options': {'redactValue': 'XXXXX'}}])]}
 #      cmDict = {'dict_item': [('WP2_TOPIC', 'fhir-wp2'), ('HEIR_KAFKA_HOST', 'kafka.fybrik-system:9092'),('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: [id valueQuantity.value]', 'columns': ['id', 'valueQuantity.value'], 'options': {'redactValue': 'XXXXX'}}, {'action': 'Statistics', 'description': 'statistics on columns: [valueQuantity.value]', 'columns': ['valueQuantity.value']}])]}
  #      cmDict = {'dict_items': [('WP2_TOPIC', 'fhir-wp2'), ('HEIR_KAFKA_HOST', 'kafka.fybrik-system:9092'), ('VAULT_SECRET_PATH', None), ('SECRET_NSPACE', 'fybrik-system'), ('SECRET_FNAME', 'credentials-els'), ('S3_URL', 'http://s3.eu.cloud-object-storage.appdomain.cloud'), ('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: [id valueQuantity.value]', 'columns': ['id', 'valueQuantity.value'], 'options': {'redactValue': 'XXXXX'}}, {'action': 'Statistics', 'description': 'statistics on columns: [valueQuantity.value]', 'columns': ['valueQuantity.value']}])]}
    else:
        cmDict = cmReturn.get('data', [])
    print("cmDict = ", cmDict)

    app.run(port=FLASK_PORT_NUM, host='0.0.0.0')

if __name__ == "__main__":
    main()
