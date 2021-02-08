#
# Sending a telemetry batch to Azure IoT Central (or the Azure IoT Hub) with Python
# 
# The Azure IoT Python SDK only supports MQTT and sending a batch only works using HTTPS
# so it was necessary to write a function to use the IoT Hub REST API for devices to send
# a batch of telemetry.
#
# Batching works like a multiplexer/de-multiplexer.  The individual telemetry messages are bundled into a 
# single POST body and sent to the IoT Hub.  When received at the IoT Hub the messages are de-multiplexed 
# into the individual messages and passed into IoT Central.
#
# Also included is a very simple DPS registration routine using the DPS HTTPS REST interface.
#


import requests
import base64
import json
import hmac
import hashlib
import binascii
import calendar 
from time import time, gmtime, sleep
from urllib import parse
from urllib.parse import urlparse
from datetime import datetime, timedelta


# derives a symmetric device key for a device id using the group symmetric key
def derive_device_key(device_id, group_symmetric_key):
    message = device_id.encode("utf-8")
    signing_key = base64.b64decode(group_symmetric_key.encode("utf-8"))
    signed_hmac = hmac.HMAC(signing_key, message, hashlib.sha256)
    device_key_encoded = base64.b64encode(signed_hmac.digest())
    return device_key_encoded.decode("utf-8")


# Simple device registration with DPS using the REST interface
def provision_device_with_dps(device_id, scope_id, group_symmetric_key, model_id=None):
    body = ""
    if model_id:
        body = "{\"registrationId\":\"%s\", \"payload\":{\"iotcModelId\":\"%s\"}}" % (device_id, model_id)
    else:
        body = "{\"registrationId\":\"%s\"}" % device_id

    expires = calendar.timegm(gmtime()) + 3600
    device_key = derive_device_key(device_id, group_symmetric_key)

    sr = scope_id + "%2fregistrations%2f" + device_id
    sig_no_encode = derive_device_key(sr + "\n" + str(expires), device_key)
    sig_encoded = parse.quote(sig_no_encode, safe='~()*!.\'')

    auth_string = "SharedAccessSignature sr=" + sr + "&sig=" + sig_encoded + "&se=" + str(expires) + "&skn=registration"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "keep-alive",
        "UserAgent": "prov_device_client/1.0",
        "Authorization" : auth_string
    }

    # kick off the registration process
    uri = "https://global.azure-devices-provisioning.net/%s/registrations/%s/register?api-version=2019-03-31" % (scope_id, device_id)
    target = urlparse(uri)
    r = requests.put(uri, data=body, headers=headers)
    response_json = json.loads(r.text)
    if "errorcode" not in response_json:
        uri = "https://global.azure-devices-provisioning.net/%s/registrations/%s/operations/%s?api-version=2019-03-31" % (scope_id, device_id, response_json['operationId'])
        # loop up to five looking for completed registration status
        for i in range(0,5,1):
            target = urlparse(uri)
            r = requests.get(uri, headers=headers)
            response_json = json.loads(r.text)
            if "status" in response_json:
                if response_json["status"] == "assigning":
                    sleep(1) # wait a second and look again
                else:
                    return response_json["registrationState"]["assignedHub"] # return the hub host
    return ""


# main function for sending batch data to the IoT hub
def send_batch_data(device_id, hub_host, device_key, data):
    def gen_sas_token(uri, key, expiry):
        ttl = time() + expiry
        sign_key = "%s\n%d" % ((parse.quote_plus(uri)), int(ttl))
        signature = base64.b64encode(hmac.HMAC(base64.b64decode(key), sign_key.encode('utf-8'), hashlib.sha256).digest())
        rawtoken = {
            'sr' :  uri,
            'sig': signature,
            'se' : str(int(ttl))
        }
        return 'SharedAccessSignature ' + parse.urlencode(rawtoken)

    def send_now(url, headers, payload, start_index, batch_size):
        errorDuringSend = False
        r = requests.post('https://'+url+'?api-version=2020-09-30', data=payload, headers=headers) 
        if (r.status_code >= 300):
            errorDuringSend = True
            for z in range(start_index, start_index + batch_size):
                data[z]["error"] = True
                data[z]["error-info"] = {'code':r.status_code, 'reason': r.reason}
        else:
            for z in range(start_index, start_index + batch_size):
                data[z]["error"] = False
        return errorDuringSend

    # error indicator if False no send errors, if True there was an error in sending the data to IoT Hub and is indicated int the data list
    errorDuringSend = False

    # maximum IoT Hub message size (currently 256KB)
    max_message_size = 255 * 1024

    # TTL for the SAS token - set to 1 hour
    token_ttl = 3600

    # build the headers and make the POST request
    path = '/devices/{0}/messages/events'.format(device_id)
    url = '{0}{1}'.format(hub_host, path)
    authorization_token = gen_sas_token(url, device_key, token_ttl) # this could be cached for the duration of the TTL to reduce compute
    headers = {'iothub-to': path, 'Content-type': 'application/vnd.microsoft.iothub.json', 'Authorization': authorization_token, 'User-Agent': 'azure-iot-device/1.17.3 (node v14.12.0; Windows_NT 10.0.19042; x64)'}

    # build the batch payload for the batch API call
    # format: {"body":"<Base64 Message1>","properties":{"<key>":"<value>"}},
    payload = '['
    first = True
    start_index = 0
    batch_size = 0
    for x in data:
        encoded = base64.b64encode(str.encode(json.dumps(x)))
        payload_chunk = '{{"body":"{0}"'.format(encoded.decode('utf-8'))
        if "properties" in x.keys():
            payload_chunk += ', "properties":{0},"$.ct":"application%2Fjson","$.ce":"utf-8"}}'.format(x["properties"])
        else:
            payload_chunk += ',"properties":{"$.ct":"application%2Fjson","$.ce":"utf-8"}}'
        if (len(payload) + 2 + len(payload_chunk) < max_message_size):
            if (not first):
                payload += ','
            else:
                first = False
            payload += payload_chunk
            batch_size += 1
        else:
            payload += ']'
            errorDuringSend = send_now(url, headers, payload, start_index, batch_size)
            payload = '[' + payload_chunk
            start_index = start_index + batch_size
            batch_size = 1
    payload += ']'

    errorDuringSend = send_now(url, headers, payload, start_index, batch_size)

    return errorDuringSend


# calling the batch send

# batch data as a list of dictionary items
# note: the property 'iothub-app-iothub-creation-time-utc' allows the ingestion time into the hub to be overridden with the supplied UTC ISO-3339 format time stamp
# other custom message properties can be included here as well if needed.  The properties dictionary is optional.
data = [
        { 'temp': 10, 'humidity': 70, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format((datetime.utcnow()- timedelta(hours=0, minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))} },
        { 'temp': 20, 'humidity': 80, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format((datetime.utcnow()- timedelta(hours=0, minutes=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))} },
        { 'temp': 30, 'humidity': 90, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format((datetime.utcnow()- timedelta(hours=0, minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))} },
        { 'temp': 40, 'humidity': 100, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format((datetime.utcnow()- timedelta(hours=0, minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ"))} },
        { 'temp': 50, 'humidity': 110, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format((datetime.utcnow()- timedelta(hours=0, minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))} },
        { 'temp': 60, 'humidity': 120, 'properties':{'iothub-app-iothub-creation-time-utc':'{0}'.format(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))}}
    ]

# fill in the device identity
device_id = "< Enter in a device identity, can be any valid name and does not need to be already registered in IoT Central >"
# fill in the information for your IoT Central application
scope_id = "< Enter the scope identity for your IoT Central application, found in Administration -> Device connection >"
group_symmetric_key = "< Enter the Group SAS token for your IoT Central application, found in Administration -> Device connection >"
model_id = "< Enter the model identity for the device model you would like the device identified with, found in Device templates -> select the device template -> select the model interface -> click 'View identity' >"

# register the device with DPS to get the hub host name
device_symmetric_key = derive_device_key(device_id, group_symmetric_key)
iot_hub_host = provision_device_with_dps(device_id, scope_id, group_symmetric_key, model_id)

if (iot_hub_host != ""):
    errorDuringSend = send_batch_data(device_id, iot_hub_host, device_symmetric_key, data)

    if (errorDuringSend):
        print("The following data was unable to be sent:")
        for x in data:
            if (x["error"]):
                print("\tdata:{0}".format(x))   
    else:
        print("Success sending batch")
else:
    print("Something went wrong with the DPS registration")