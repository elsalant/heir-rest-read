#
# Copyright 2022 IBM Corp.
# SPDX-License-Identifier: Apache-2.0
#
import logging

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
from sqlUtils import SQLutils

FLASK_PORT_NUM = 5559  # this application

ACCESS_DENIED_CODE = 403
ERROR_CODE = 406
BLOCK_CODE = 501
VALID_RETURN = 200

TEST = False  # allows testing outside of Fybrik/Kubernetes environment
logger = logging.getLogger(__name__)

if TEST:
    DEFAULT_FHIR_HOST = 'https://localhost:9443/fhir-server/api/v4/'
else:
    DEFAULT_FHIR_HOST = 'https://ibmfhir.fybrik-system:9443/fhir-server/api/v4/'

# for testing only.  Not in testing mode we get these values from the secret keys
DEFAULT_FHIR_USER = 'fhiruser'
DEFAULT_FHIR_PW = 'change-password'

DEFAULT_KAFKA_TOPIC = 'fhir-wp2-logging'
DEFAULT_KAKFA_HOST = 'kafka.heirauditingmechanism:9092'

BLOCKCHAIN_HOST = 'http://heirauditclient.heirauditingmechanism:8081/'

kafka_host = os.getenv("HEIR_KAFKA_HOST") if os.getenv("HEIR_KAFKA_HOST") else DEFAULT_KAKFA_HOST
kafka_topic = os.getenv("HEIR_KAFKA_TOPIC") if os.getenv("HEIR_KAFKA_TOPIC") else DEFAULT_KAFKA_TOPIC

FIXED_SCHEMA_ROLE = 'Role'
FIXED_SCHEMA_ORG = 'aud'  # Use the audience role?

DEFAULT_TIMEWINDOW = 3560  # days - should be 14
HIGH_THRESHOLD_DEFAULT = 8.3
LOW_THRESHOLD_DEFAULT = 4

fhir_host = os.getenv("HEIR_FHIR_HOST") if os.getenv("HEIR_FHIR_HOST") else DEFAULT_FHIR_HOST
fhir_user = os.getenv("HEIR_FHIR_USER") if os.getenv("HEIR_FHIR_USER") else DEFAULT_FHIR_USER

time_window = os.getenv("HEIR_TIMEWINDOW") if os.getenv("HEIR_TIMEWINDOW") else DEFAULT_TIMEWINDOW

app = Flask(__name__)
cmDict = {}
sqlUtils = SQLutils()

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
    try:
        requester = cmDict['SUBMITTER']
    except:
        requester = 'EliotSalant'
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
#    queryURL = fhir_host or blockchain host, depending on the original URL
    # This is sort of a hack - nearly all the calls to the blockchain contain 'Log' in them.
    # Use this to determine if we need to redirect the query to the blockchain mgr instead of the FHIR server
    blockchainQuery = False
    print('read_from_fhir - cmDict = ')
    print(cmDict)
    if 'Log' in queryString:
        print('redirecting to blockchain')
        queryURL = BLOCKCHAIN_HOST
        blockchainQuery = True
    else:
        queryURL = cmDict['FHIR_SERVER']
    if TEST:
        fhiruser = fhir_user
        fhirpw = DEFAULT_FHIR_PW
    else:
        if ~blockchainQuery:
            fhiruser, fhirpw = getSecretKeys()
    print('queryURL = ' + queryURL)
    params = ''
 #   auth = (fhir_user, fhir_pw)
    auth = (fhiruser, fhirpw)

    returnedRecord = handleQuery(queryURL, queryString, auth, params, 'GET')
    if returnedRecord == None:
        return(['{"ERROR" : "returnedRecord empty!"}'], ERROR_CODE)
    # Strip the bundle information out and convert to data frame
    recordList = []
    if blockchainQuery == True:
        return(returnedRecord, VALID_RETURN)
    try:
        for record in returnedRecord['entry']:
            print("bundle detected")
            recordList.append(json.dumps(record['resource'], indent=2))
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
    try:
        secret_namespace = cmDict['SECRET_NSPACE']
        secret_fname = cmDict['SECRET_FNAME']
        print("secret_fname = " + secret_fname + " secret_namespace = " + secret_namespace)
        secret = v1.read_namespaced_secret(secret_fname, secret_namespace)
        fhiruser = base64.b64decode(secret.data['fhiruser'])
        fhirpw = base64.b64decode(secret.data['fhirpasswd'])
        print('getSecretKeys: fhiruser = ' + fhiruser.decode('ascii') + ' fhirpw = ' + fhirpw.decode('ascii'))
        return(fhiruser.decode('ascii'), fhirpw.decode('ascii'), )
    except:
        print('getSecretKeys failed!')
        return('N/A','N/A')

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

def redactEntry(dfLine, df):
    pass

# Pass in the data to be redacted as jsonList, along with the redaction policies
# origFHIR is required if we are doing a JOIN, as we need to translate this to SQL
def apply_policy(jsonList, policies, origFHIR, role, blockChainCall):
    df = pd.json_normalize(jsonList)
    print('In apply_policy, df.keys = ')
    print(df)
    redactedData = []
    # Redact df based on policy returned from the policy manager
    meanStr = ''
    stdStr = ''  # standard deviation
    std = ''
   # cleanPatientId = df['subject.reference'][0].replace('/', '-')
    if policies['transformations']:
        print('inside apply_policy. Length policies = ', str(len(policies['transformations'])), " type(policies) = ", str(type(policies)))
        print(policies)
    if policies['transformations'] == None or len(policies['transformations']) == 0:
        print('No transformations found!')
        return (str(df.to_json()), VALID_RETURN )
    # There can be a number of policies that need to be applied.  If we have a JOIN, this needs to be done
    # first, before the the redaction.  In that case, the case, the data returned by the JOIN needs to have the
    # redaction applied to it.  Make sure that the JoinResource actions is the first in the list
    if len(policies['transformations']) > 1:
        for index, value in enumerate(policies['transformations']):
            if policies['transformations'][index]['action'] == 'JoinResource':
                policies['transformations'] = [policies['transformations'][index]] + policies['transformations']
                policies['transformations'].pop(index+1)
                break

    for policy in policies['transformations']:
        action = policy['action']
        print('Action = ' + action)
        print('policy = ')
        print(policy)
        if action == '':
            return (str(df.to_json()), VALID_RETURN)

    # Allow specifying a particular attribute for a given resource by specifying the in policy file the
    # the column name as <resource>.<column_name>
        dfToRows = []
        if action == 'DeleteColumn':
            try:
                for col in policy['columns']:
                    if '.' in col:
                        (resource, col) = col.split('.')
                        print("resource, attribute specified: " + resource + ", " + col)
                        if (df['resourceType'][0]) != resource:
                            continue
                    df.drop(col, inplace=True, axis=1)
            except:
                print("No such column " + col + " to delete")
            for i in df.index:
                jsonList = [json.loads(x) for x in dfToRows]
 #           return (jsonList, VALID_RETURN)
            continue

        elif action == 'RedactColumn':
            if role.lower() == policy['noredact-role'].lower():   # hack for blockchain
                print('RedactColumn: no redaction being done!')
                continue
            replacementStr = policy['options']['redactValue']
            for col in policy['columns']:
                # Flattening the FHIR means that an attribute may now appears with one or more '.', so the following
                # code is no longer valid
                '''
                if '.' in col:
    # We can either be passing something of the form:  resource.attribute, or attribute, where attribute
    # itself may contain a '.'.  Take the result of the first split and see if that is equal to resourceType to differentiate
                    (resourceCandidate, colCandidate) = col.split('.',1)
                    if resourceCandidate == df['resourceType'][0]:
                        col = colCandidate
                    print("resource, attribute specified: " + resourceCandidate + ", " + col)
 '''
                print('trying to replace ' + col + ' with ' + replacementStr  + ' in df: ')
                try:
        # Replace won't replace floats or ints.  Instead, convert to column to be replaced to a string
        # before replacing
      #              df[col].replace(r'.+', replacementStr, regex=True, inplace=True)
                    df[col]= df[col].astype(str).str.replace(r'.+', replacementStr, regex=True)
                except:
                    print("No such column " + col + " to redact")
            for i in df.index:
                dfToRows.append(df.loc[i].to_json())
            jsonList = [json.loads(x) for x in dfToRows]
            df = pd.json_normalize(jsonList)
            jsonOut = df.to_json()   # change single quotes to double quotes
            return(str(jsonOut), VALID_RETURN)
 #           return str(jsonList).replace('\'', '\"' ), VALID_RETURN
 #           continue

        if action == 'BlockResource':
        #    if policy['transformations'][0]['columns'][0] == df['resourceType'][0]:
            if df['resourceType'][0] in policy['columns']:
                return('{"result": "Resource blocked by policy!!"}', BLOCK_CODE)
            else:
                print('No resource to block!. resourceType =  ' + df['resourceType'][0] + \
                      ' policy[\'columns\'][0] = ' + df['resourceType'][0] in policy['columns'][0])
                continue
        # This redaction was requested for the NSE use case.
        # If there is no consent for an individual patient record (row), redact all PII from the row,
        # else reveal all
        if action == 'JoinAndRedact':
            if blockChainCall == True:   # hack for blockchain support
                continue
            ###
            joinedJSON = sqlJoin(policy, jsonList, origFHIR)
            print('df.keys() = ', df.keys())
            inTimePeriodDF = pd.json_normalize(joinedJSON)
            print('inTimePeriodDF.keys() = '+ inTimePeriodDF.keys())
            if inTimePeriodDF.size:
                outOfTimePeriodDF = df.loc[~df['id'].isin(inTimePeriodDF['id'])]
            else:
                outOfTimePeriodDF = []
            print('outOfTimePeriodDF.size = '+str(outOfTimePeriodDF.size))
            print('inTimePeriodDF.size = ' + str(inTimePeriodDF.size))
            print('df.size = ' + str(df.size))
            '''
            current_timestamp = datetime.now(timezone.utc)
            whereclause = policy['whereclause']
            joinTable = policy['joinTable']
            # Call in to FHIR to get the join resource (i.e. 'Consent'), and put the results into a df.
            # The passed 'joinTable' value must be the name of the FHIR resource
            joinQuery = joinTable
            consentTuple, status = read_from_fhir(joinQuery)
            consentDF = pd.json_normalize(consentTuple[0])

            end_consentList = []
            # Add a new column to the consentDF df which is "end_date" and is in timestamp format
            for index in consentDF.index:
                end_consentList.append(datetime.strptime(consentDF['provision.provision'][index][0]['period']['end'], '%Y-%m-%dT%H:%M:%S%z'))
            print('end_consentList = ' + str(end_consentList))
            consentDF['end_consent'] = end_consentList
            print('consentDF["patient.reference"] = ' + str(consentDF['patient.reference']))
            print('df[subject.reference] = ' + str(df['subject.reference']))
            # Now, drop all entries where the consent has expired
            cleanedConsentDF = consentDF[consentDF['end_consent'] >= current_timestamp]
            outOfTimePeriodDF = df.loc[~df['subject.reference'].isin(cleanedConsentDF['patient.reference'])]
            inTimePeriodDF = df.loc[df['subject.reference'].isin(cleanedConsentDF['patient.reference'])]
            '''
  # Redact the dataframes for outOfTimePeriodDF and then append these results to the unredacted inTimePeriodDF
            if  not TEST:
                replacementStr = policy['options']['redactValue']
            else:
                replacementStr = 'XXXX'
            for col in policy['columns']:
                print('trying to replace ' + col + ' with ' + replacementStr + ' in outOfTimePeriod: ')
                try:
                    # Replace won't replace floats or ints.  Instead, convert to column to be replaced to a string
                    # before replacing
                    #              df[col].replace(r'.+', replacementStr, regex=True, inplace=True)
                    if not outOfTimePeriodDF.empty:
                        outOfTimePeriodDF[col] = outOfTimePeriodDF[col].astype(str).str.replace(r'.+', replacementStr, regex=True)
                except:
                    print("No such column " + col + " to redact")
                    if not outOfTimePeriodDF.empty:
                        print('available columns (outOfTimePeriodDF) = ' + str(outOfTimePeriodDF.keys()))

            for i in outOfTimePeriodDF.index:
                dfToRows.append(outOfTimePeriodDF.loc[i].to_json())
            for i in inTimePeriodDF.index:
                dfToRows.append(inTimePeriodDF.loc[i].to_json())
            jsonList = [json.dumps(json.loads(x)) for x in dfToRows]
            print('JoinAndRedact about to return ' + str(jsonList))
            return str(jsonList), VALID_RETURN

        # df.loc[datetime.strptime(consentDF['provision.provision'][0][0]['period']['start'], '%Y-%m-%dT%H:%M:%S%z')  > current_timestamp]
        # In this case, the policy is specifying another data source (FHIR resource) to JOIN with.
        # 1. Put the returned query results from the original FHIR query into an SQLite table
        # 2. Execute a FHIR query to get all the records in the resource to be joined and put in an SQLite table
        # 3. Translate the input FHIR query to SQL
        # 4. Reformulate the query based on the return from the Policy Manager to add the JOIN
        # 5. Execute an SQL query on this new query
        # 6. Handle redactions
        if action == 'JoinResource':
            if blockChainCall == True:  # hack for blockchain support
                continue
            joinedJSON = sqlJoin(policy, jsonList, origFHIR)
            '''
            whereclause = policy['whereclause']
            joinclause = policy['joinStatement']
            joinTable = policy['joinTable']
            # Give the name the same name as the requested resource
            tableName = df['resourceType'][0]
            logger.info('building table of name' + tableName)
            sqlUtils.buildSQLtableFromJson(jsonList,'Observation')
            # Call in to FHIR to get the join resource values, and put the results into a table.
            # The passed 'joinTable' value must be the name of the FHIR resource
            joinQuery = joinTable
            joinJSON, status = read_from_fhir(joinQuery)
            logger.info('building JOIN table of name' + joinTable)
            sqlUtils.buildSQLtableFromJson(joinJSON[0], joinTable)
            # The original FHIR query already applied any selection criteria.  We can therefore do a
            # SELECT * on the returned data stored in the temporary view
            # No need to do anything with the returned aliasDict, since the original query is FHIR without aliasing
            origSQL = sqlUtils.fhirToSQL(origFHIR)
            joinQuery, aliasDict = sqlUtils.reformulateQuery(origSQL, whereclause, joinclause)
            joinedJSON = sqlUtils.querySQL(joinQuery)
            # If we still have other transformation actions to handle - i.e. more than one transform in policies,
            #  reset the original df and continue
            '''
            if len(policies['transformations']) > 1:
                df = pd.json_normalize(joinedJSON)
                continue
            else:
                return (joinedJSON, VALID_RETURN)

        elif action == 'Statistics':
            for col in policy['columns']:
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
        else:
            return('{"Unknown transformation": "'+ action + '"}', ERROR_CODE)
#    print("after redaction, returning " + str(df.to_json()))
    return (str(df.to_json()), VALID_RETURN)

def timeWindow_filter(df):
    print("keys = ", df.keys())
    # drop rows that are outside of the timeframe
    df.drop(df.loc[(pd.to_datetime(df['effectivePeriod.start'], utc=True) + timedelta(days=time_window) < datetime.now(timezone.utc)) | (df['resourceType'] != 'Observation')].index, inplace=True)
    return df

def sqlJoin(policy, resourceList, origFHIR):
    observationDF = pd.json_normalize(resourceList)
    whereclause = policy['whereclause']
    joinclause = policy['joinStatement']
    joinTable = policy['joinTable']
    # Give the name the same name as the requested resource
    tableName = observationDF['resourceType'][0]
    logger.info('building table of name' + tableName)
    print('resourceList = ', str(resourceList))
    sqlUtils.buildSQLtableFromJson(resourceList, 'Observation')
    # Call in to FHIR to get the join resource values, and put the results into a table.
    # The passed 'joinTable' value must be the name of the FHIR resource
    joinQuery = joinTable
    joinJSON, status = read_from_fhir(joinQuery)
    print('status = ', str(status))
    print('joinJSON = ', str(joinJSON))
    logger.info('building JOIN table of name' + joinTable)
    sqlUtils.buildSQLtableFromJson(joinJSON, joinTable)
    # The original FHIR query already applied any selection criteria.  We can therefore do a
    # SELECT * on the returned data stored in the temporary view
    # No need to do anything with the returned aliasDict, since the original query is FHIR without aliasing
    origSQL = sqlUtils.fhirToSQL(origFHIR)
    joinQuery, aliasDict = sqlUtils.reformulateQuery(origSQL, whereclause, joinclause)
    joinedJSON = sqlUtils.querySQL(joinQuery)
    print('sqlJoin: joinedJSON = ')
    print(joinedJSON)
    # If we still have other transformation actions to handle - i.e. more than one transform in policies,
    #  reset the original df and continue
#    if len(policies['transformations']) > 1:
#        df = pd.json_normalize(joinedJSON)
#        continue
#    else:
    return (joinedJSON)

# @app.route('/query/<queryString>')
# def query(queryString):
# Catch anything
@app.route('/<path:queryString>',methods=['GET', 'POST', 'PUT'])
def getAll(queryString=None):
    global cmList
    global cmDict
    print("queryString = " + queryString)
    print('request.url = ' + request.url)
    if 'Log' in request.url:
        blockchainRequest = True   # hack required to avoid policy mean for consent
    else:
        blockchainRequest = False
# Handle authentication in the header
    noJWT = True
    payloadEncrypted = request.headers.get('Authorization')
    organization = None
    role = None
    givenName = 'None'
    surName = 'None'
    intent = ''
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
            intent = decryptJWT(payloadEncrypted, 'Intent')
        except:
            print("Error: no Intent in JWT!")
            intent = 'ERROR NO INTENT!'
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
    print('Surname = ' + surName + ' GivenName = ' + givenName + ' role = '+ role + ' organization = ' + organization + ' Intent = ' + intent)
#   Role in JWT needs to match role of requestor from original FybrikApplication deployment
    requester = checkRequester()  # from the FybrikApplication
    timeOut = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Hack for testing without JWT
    queryRequester = role if noJWT else givenName+surName
    # assetID is used for logging only and may not be supplied
    # cmList now contains a list of dictionaries, one dictionary for each asset
    # As a semi-hack, for blockchain, use the dictionary associated with the asset in the rest-blockchain namespace
    if blockchainRequest:
        for dict in cmList:
            if 'rest-blockchain' in dict['name']:
                cmDict = dict
    else:
        for dict in cmList:
            if 'rest-fhir' in dict['name']:
                cmDict = dict
                break

    print('cmDict = ', str(cmDict))
    if 'assetID' in cmDict:
        assetID = cmDict['assetID']
    else:
        assetID = __name__
    intent = 'Not given'
    if cmDict['transformations'] == None:
        print('No transformations defined!')
    else:
        for i in cmDict['transformations']:
            if 'intent' in i:
                intent = i['intent']
    if (queryRequester != requester):
        print("queryRequester " + queryRequester + " != " + requester)
        jSONout = '{\"Timestamp\" : \"' + timeOut + '\", \"Requester\": \"' + str(queryRequester) + '\", \"Query\": \"' + str(queryString) + \
                    '\", \"ClientIP\": \"' + str(request.remote_addr) + '\",' + \
                  '\"assetID": \"' + str(assetID) + '\",' + \
                  '\"policyDecision\": \"' + str(cmDict['transformations']) + '\",' + \
                    '"intent\": \"' + str(intent) +'\", \"Outcome": \"UNAUTHORIZED\"}'
        logToKafka(jSONout, kafka_topic)
        return ("{\"Error\": \"Unauthorized access attempt!\"}")

    # Go out to the actual FHIR server
    print("request.method = " + request.method)
    dfBack, messageCode = read_from_fhir(queryString)  # e.g. get all Observations
    if (messageCode != VALID_RETURN):
        return ("{\"Error\": \"No information returned!\"}")
#apply_policies
    ans, messageCode = apply_policy(dfBack, cmDict, queryString, role, blockchainRequest)
    if messageCode == VALID_RETURN:
        outcome = "AUTHORIZED"
    elif messageCode == BLOCK_CODE:
        outcome = "RESTRICTED"
    else:
        outcome = "ERROR"
    # Log the query request
    # Apparently there is a bug in Fybrik that is returning a " instead of '
    # workaround
    print('policyDecision before = '+str(cmDict['transformations']))
    policyDecision = str(cmDict['transformations']).replace("\"", "\'")
    print('policyDecision after= '+policyDecision)
    jSONout = '{\"Timestamp\" : \"' + timeOut + '\", \"Requester\": \"' + str(requester) + '\", \"Query\": \"' + str(queryString) + '\",' + \
              '\"ClientIP\": \"' + str(request.remote_addr) + '\",' + \
              '\"assetID": \"' + str(assetID) + '\",' + \
              '\"policyDecision\": \"'  + str(policyDecision) + '\",' + \
              '\"intent\": \"' + str(intent) + '\",\"Outcome": \"' + str(outcome) + '\"}'
    logToKafka(jSONout, kafka_topic)
 #   print('ans = '+ str(ans))
    return(ans)
 #   return (json.dumps(ans))

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
#    global cmDict
    global cmList
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
        cmList = [{'SUBMITTER': 'EliotSalant', 'assetID': 'test1', 'SECRET_NSPACE': 'rest-fhir', 'name':'rest-fhir',
          'SECRET_FNAME': 'fhir-credentials', 'FHIR_SERVER' : 'https://localhost:9443/fhir-server/api/v4/', 'transformations': [
                {'action': 'JoinAndRedact', 'joinTable': 'Consent',
                            'whereclause': ' WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP',
                            'joinStatement': ' JOIN consent ON observation.subject_reference = consent.patient_reference ',
                            'columns': ['id', 'subject.reference', 'subject.display']},
        {'action': 'BlockResource', 'description': 'Block all data for resource: [subject.reference]',
         'columns': ['subject.reference']},
        {'action': 'JoinResource', 'description': 'Perform a JOIN', 'joinTable': 'Consent',
         'whereclause': ' WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP',
         'joinStatement': ' JOIN consent ON observation.subject_reference = consent.patient_reference '},
        {'action': 'RedactColumn', 'description': 'redact columns: [valueQuantity.value subject.reference]',
         'intent': 'research', 'columns': ['valueQuantity.value', 'subject.reference'],
         'options': {'redactValue': 'XXXXX'}}]}]
 #       cmDict = {'dict_item': [
 #           ('transformations', [{'action': 'JoinResource', 'description': 'Perform a JOIN on the Consent resource',
 #                                 'joinTable': 'Consent',
 #                                 'whereclause': ' WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP',
 #                                 'joinStatement': ' JOIN consent ON observation.subject_reference = consent.patient_reference '}])]}
 #       cmDict = {'dict_item': [
 #           ('transformations', [{'action': 'JoinResource', 'description': 'Perform a JOIN on the Consent resource',
 #                                'joinTable': 'Consent',
 #                                 'whereclause': ' WHERE consent.provision_provision_0_period_end > CURRENT_TIMESTAMP',
 #                                'joinStatement': ' JOIN consent ON observation.subject_reference = consent.patient_reference '},
 #                                {'action': 'RedactColumn', 'description': 'Redact PII fields',
 #                                 'joinTable': 'Consent',
 #                                 'columns': ['valueQuantity.value','subject.display', 'text.div', 'subject.reference'],
 #                                                 'options': {'redactValue': 'XXXXX'}}])]}
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redact columns: [valueQuantity.value id]',
   #             'columns': ['valueQuantity.value', 'id'], 'options': {'redactValue': 'XXXXX'}}]), ('assetID', 'sql-fhir/observation-json')]}
   #    cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redact columns: [valueQuantity.value id]',
   #          'columns': ['valueQuantity.value', 'id'], 'options': {'redactValue': 'XXXXX'}}]), ('assetID', 'sql-fhir/observation-json')]}
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: Patient', 'columns': ['Patient'], 'options': {'redactValue': 'XXXXX'}}])]}
   #     cmDict = {'dict_item': [('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: ',
   #                                               'columns': ['valueQuantity.value','subject.display', 'text.div', 'subject.reference'],
   #                                               'options': {'redactValue': 'XXXXX'}}])]}
   # cmDict = {'dict_item': [
   #     ('transformations', [{'action': 'BlockResource', 'description': 'redact columns: [valueQuantity.value id]',
   #                           'columns': ['valueQuantity.value', 'id'], 'options': {'redactValue': 'XXXXX'}},
   #                          {'action': 'ReturnIntent', 'description': 'return intent',
   #                           'columns': ['N/A'], 'intent': 'research'}]), ('assetID', 'sql-fhir/observation-json')]}
 #      cmDict = {'dict_item': [('WP2_TOPIC', 'fhir-wp2'), ('HEIR_KAFKA_HOST', 'kafka.fybrik-system:9092'),('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: [id valueQuantity.value]', 'columns': ['id', 'valueQuantity.value'], 'options': {'redactValue': 'XXXXX'}}, {'action': 'Statistics', 'description': 'statistics on columns: [valueQuantity.value]', 'columns': ['valueQuantity.value']}])]}
  #      cmDict = {'dict_items': [('WP2_TOPIC', 'fhir-wp2'), ('HEIR_KAFKA_HOST', 'kafka.fybrik-system:9092'), ('VAULT_SECRET_PATH', None), ('SECRET_NSPACE', 'fybrik-system'), ('SECRET_FNAME', 'credentials-els'), ('S3_URL', 'http://s3.eu.cloud-object-storage.appdomain.cloud'), ('transformations', [{'action': 'RedactColumn', 'description': 'redacting columns: [id valueQuantity.value]', 'columns': ['id', 'valueQuantity.value'], 'options': {'redactValue': 'XXXXX'}}, {'action': 'Statistics', 'description': 'statistics on columns: [valueQuantity.value]', 'columns': ['valueQuantity.value']}])]}
    else:
        cmList = cmReturn.get('data', [])
        print('length of cmList = ' + str(len(cmList)))
        # We now have a list for each data source
        # Merge into one dictionary
 #       cmDict = {cmList[0], cmList[1]}
 #       for key, value in cmDict.items():
 #           if key in cmList[0] and key in cmDict[1]:
  #              cmDict[key] = [value, cmList[1][key]]
 #       cmDict = cmList[0]  # Fix this!!
 #   print("cmDict = ", str(cmDict))

    app.run(port=FLASK_PORT_NUM, host='0.0.0.0')

if __name__ == "__main__":
    main()
