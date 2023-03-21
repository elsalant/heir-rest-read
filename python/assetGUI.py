import yaml
from kubernetes import client, config
import os
import PySimpleGUI as sg

def main():
    api_client = initializeKubernetesClient()
    assets = getAllAssets(api_client,GROUP,VERSION,NAMESPACE,PLURAL)
#    print('number of assets = ' + str(len(assets))+ ' '+str(assets))
    assetLine = []
    for asset in assets:
        assetName = asset['metadata']['name']
        assetData= getAssetYAML(api_client,GROUP,VERSION,NAMESPACE,PLURAL,assetName)
        yaml_data = yaml.safe_load(assetData)
        attribList = yaml_data['spec']['metadata']['columns']
        createGUI(assetLine, attribList)
        yaml_data['spec']['metadata']['columns'] = attribList
        updateAsset(api_client, yaml_data)
 #       update_yamlfile(yaml_data, assetName)
        os.system('kubectl apply -f '+ assetName)

def updateAsset(api_client, yaml_data):
    api_client.patch_namespaced_custom_object(
        GROUP, VERSION, NAMESPACE, PLURAL,
        yaml_data["metadata"]["name"],
        yaml_data
    )

def update_yamlfile(yaml_data, ASSET_FILE):
    ff = open(ASSET_FILE, "w+")
    yaml.dump(yaml_data, ff)
    ff.close()

def initializeKubernetesClient():
    try:
        config.load_kube_config()
    except:
        # Load in-cluster configuration - but the graphics will fail anyway....
        config.load_incluster_config()
    api_client = client.CustomObjectsApi()
    return(api_client)

def getAllAssets(api_client, group, version, namespace, plural):
    resources = api_client.list_namespaced_custom_object(
        group,
        version,
        namespace,
        plural
    )
    return (resources['items'])

def getAssetYAML(api_client, group, version, namespace, plural, assetName):
    # Get the details of the CRD
    crd = api_client.get_namespaced_custom_object(
        group,
        version,
        namespace,
        plural,
        assetName
    )

    # Convert the CRD to YAML
    crd_yaml = yaml.safe_dump(crd, default_flow_style=False)
    return (crd_yaml)

def createGUI(assetNames, attribList):
    font = ("Arial", 18)
    for entry in attribList:
        assetNames.append(entry['name']+' : '+str(entry['tags']['PII']))
    attribute_list_column = [
        [sg.Listbox(values=[], enable_events=True, size=(40, 10), key="-ATTR LIST-", font=font)],
    ]
    button_column = [
        [sg.Button("OK")]
    ]
    layout = [[sg.Text("Toggle values of PII fields", font= ("Arial", 20))],
              [sg.Column(attribute_list_column)],
              [sg.Column(button_column)]]
    window = sg.Window("Fields to be redacted", layout, finalize=True)
    window["-ATTR LIST-"].update(assetNames)
    while True:
        event, values = window.read()
        # End program if user closes window or
        # presses the OK button
        if event == '-ATTR LIST-':
            selected_entry = values['-ATTR LIST-'][0]
            # Now toggle the PII value
            selected_index = window[event].get_indexes()[0]
            piiValue = attribList[selected_index]['tags']['PII']
            piiValue = not piiValue
            attribList[selected_index]['tags']['PII'] = piiValue
            assetNames = []
            for entry in attribList:
                assetNames.append(entry['name'] + ' : ' + str(entry['tags']['PII']))
            window["-ATTR LIST-"].update(assetNames)
            print(assetNames[selected_index])
        if event == "OK" or event == sg.WIN_CLOSED:
            break

    window.close()

if __name__ == "__main__":
    GROUP = "katalog.fybrik.io"
    VERSION = "v1alpha1"
    PLURAL = "assets"
    NAMESPACE = os.getenv("ASSET_NAMESPACE") if os.getenv("ASSET_NAMESPACE") else 'rest-fhir'

    main()