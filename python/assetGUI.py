import yaml
import json
import os
import PySimpleGUI as sg

def main():
    ASSET_FILE = os.getenv("ASSET_FILE") if os.getenv("ASSET_FILE") else "/Users/eliot/projects/HEIR/code/heir-2dhalf/heir-rest-read/asset.yaml"
    with open(ASSET_FILE, "r") as file:
        yaml_data = yaml.safe_load(file)
    attribList = yaml_data['spec']['metadata']['columns']
    createGUI(attribList)
    yaml_data['spec']['metadata']['columns'] = attribList
    update_yamlfile(yaml_data, ASSET_FILE)
    os.system('kubectl apply -f '+ASSET_FILE)

def update_yamlfile(yaml_data, ASSET_FILE):
    ff = open(ASSET_FILE, "w+")
    yaml.dump(yaml_data, ff)
    ff.close()

def createGUI(attribList):
    font = ("Arial", 18)
    assetNames = []
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
    main()