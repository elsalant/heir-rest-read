import pandas as pd
import json
import io
import sqlite3
from flatten_json import flatten
import sqlparse
import re

joinAdded = False

TEST = False
if TEST:
    DB_FILE = '/Users/eliot/tmp/heirsql.db'
else:
    DB_FILE = '/tmp/heirsql.db'

if TEST:
    consentJson = '''
    {
      "resourceType": "Consent",
      "id": "consent-example-Out",
      "text": {
        "status": "generated"
      },
      "status": "active",
      "scope": {
        "coding": [
          {
            "system": "http://terminology.hl7.org/CodeSystem/consentscope",
            "code": "patient-privacy"
          }
        ]
      },
      "category": [
        {
          "coding": [
            {
              "system": "http://loinc.org",
              "code": "59284-0"
            }
          ]
        }
      ],
      "patient": {
        "reference": "Patient/f001",
        "display": "P. van de Heuvel"
      },
      "dateTime": "2015-11-18",
      "organization": [
        {
          "reference": "Organization/f001"
        }
      ],
      "sourceAttachment": {
        "title": "The terms of the consent in lawyer speak."
      },
      "policyRule": {
        "coding": [
          {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "OPTOUT"
          }
        ]
      },
      "provision": {
        "actor": [
          {
            "role": {
              "coding": [
                {
                  "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                  "code": "CST"
                }
              ]
            },
            "reference": {
              "reference": "Organization/f001"
            }
          }
        ]
      }
    }
    '''

    observationJson = '''{
      "resourceType": "Observation",
      "id": "f003",
      "text": {
        "status": "generated"
      },
      "identifier": [
        {
          "use": "official",
          "system": "http://www.bmc.nl/zorgportal/identifiers/observations",
          "value": 6325
        }
      ],
      "status": "final",
      "code": {
        "coding": [
          {
            "system": "http://loinc.org",
            "code": "11557-6",
            "display": "Carbon dioxide in blood"
          }
        ]
      },
      "subject": {
        "reference": "Patient/f001",
        "display": "P. van de Heuvel"
      },
      "effectivePeriod": {
        "start": "2013-04-02T10:30:10+01:00",
        "end": "2013-04-05T10:30:10+01:00"
      },
      "issued": "2013-04-03T15:30:10+01:00",
      "performer": [
        {
          "reference": "Practitioner/f005",
          "display": "A. Langeveld"
        }
      ],
      "valueQuantity": {
        "value": 6.2,
        "unit": "kPa",
        "system": "http://unitsofmeasure.org",
        "code": "kPa"
      },
      "interpretation": [
        {
          "coding": [
            {
              "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
              "code": "H",
              "display": "High"
            }
          ]
        }
      ],
      "referenceRange": [
        {
          "low": {
            "value": 4.8,
            "unit": "kPa",
            "system": "http://unitsofmeasure.org",
            "code": "kPa"
          },
          "high": {
            "value": 6.0,
            "unit": "kPa",
            "system": "http://unitsofmeasure.org",
            "code": "kPa"
          }
        }
      ]
    }'''

class SQLutils:
    def __init__(self):
        sqlConnect = sqlite3.connect(DB_FILE)
        cursor = sqlConnect.cursor()
        return(sqlConnect, cursor)

    def buildSQLtableFromJson(self, sqlConnect, jsonInput, tableName):
        dict = flatten(json.loads(jsonInput))
        df = pd.json_normalize(dict)
        dataName = tableName+'Data'
        df.to_sql(dataName, sqlConnect, if_exists="replace" )
        sqlConnect.execute('create table ' + tableName + ' as select * from ' + dataName + ';')
        return()

    def querySQL(self, sqlConnect, strQuery):
        return(sqlConnect.execute(strQuery))

    def dropTable(self, sqlConnect, tableName):
        sqlConnect.execute('DROP TABLE IF EXISTS ' + tableName + ';')
        return()

# returns the reformulated query and a dictionary of original column names with their aliases in the event
# redaction is required
    def reformulateQuery(self, origQuery, extraWhere, extraJoins):
        global joinAdded
        # Run through the query.  Keep the SELECT and FROM clauses as-is.
        # JOIN..ON needs to be supplemented with whatever is passed as an extraJoin
        # WHERE (which does not appear as a keyword) needs to be supplemented by the extraWhere
        rebuiltQuery = ''
        tokens = sqlparse.parse(origQuery)[0]
        for index in range(0, len(tokens.tokens)):
            token = tokens[index]
            if token.is_keyword and token.value.casefold() == 'JOIN'.casefold() and joinAdded == False:
                joinAdded = True
                if extraJoins:
                    rebuiltQuery += extraJoins +'\n'
                rebuiltQuery += token.value
      #          rebuiltQuery += modifyJoin(origQuery, extraJoins)
            elif re.search('where', token.value, re.IGNORECASE):  # first add the extraWhere, stripping out "WHERE" in original token
                    if extraWhere:
                        rebuiltQuery += 'WHERE ' + extraWhere + ' AND ' + re.sub('where', '', token.value, flags=re.IGNORECASE)
                    else:
                        rebuiltQuery += token.value
            else:
                rebuiltQuery += token.value

        # Now, check to see if the SELECT clause used any aliases (i.e. "AS")
        selectQuery = self.getSelectCondition(origQuery)
        if selectQuery:
            aliasDict = getSubstitutions(selectQuery)
        return rebuiltQuery, aliasDict

    def getSelectCondition(self, origQuery):
        tokens = sqlparse.parse(origQuery)[0]
        #Get the "SELECT" statement and see if there are any "AS" subsitutions
        index = 0
        selectClause = ''
        for token in tokens:
            if str(token.ttype) == 'Token.Keyword.DML' and token.value.upper() == 'SELECT':
                while tokens[index+1].is_whitespace:
                    index += 1
                selectClause = tokens[index+1].value
                break
            index += 1
        if selectClause == '':
            print('ERROR - no SELECT found')
        print('found SELECT clause')
        return selectClause


    #Returns a dictionary of original column names and their aliases.  Note that
    def getSubstitutions(selectClause):
        splitClause = selectClause.split(',')
        aliasDict = {}  # dictionary of aliases
        for element in splitClause:
            if ' AS '.casefold() in element.casefold():
                parts = re.split(' AS ' ,element, flags=re.IGNORECASE)
                aliasDict[parts[0].strip()] = parts[1].strip()
        return aliasDict