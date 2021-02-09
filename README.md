# iot-central-batch-telemetry-with-python

## Introduction

The Azure IoT Python SDK does not support batch sending of telemetry events.  This sample shows how to send batch data to IoT Central (and IoT Hub) with Python using the Azure IoT hub REST interface.

The Azure IoT Python SDK only supports MQTT and sending a batch only works using HTTPS so it was necessary to write a function to use the IoT Hub REST API for devices to send a batch of telemetry.

Batching works like a multiplexer/de-multiplexer.  The individual telemetry messages are bundled into a single POST body and sent to the IoT Hub.  When received at the IoT Hub the messages are de-multiplexed into the individual messages and passed into IoT Central.

Also included is a very simple Device Provisioning Service (DPS) registration routine using the DPS HTTPS REST interface.

## Prerequisite

You need to install the [Requests: HTTP for humans](https://requests.readthedocs.io/en/master/) Python library using:

```
python -m pip install requests
```

## Using

Just change lines 170 - 175 to provide the necessary information about your device and the Azure IoT Central application you wish to connect to.  You need the following pieces of information:

```python
# fill in the device identity
device_id = "< Enter in a device identity, can be any valid name and does not need to be already registered in IoT Central >"
# fill in the information for your IoT Central application
scope_id = "< Enter the scope identity for your IoT Central application, found in Administration -> Device connection >"
group_symmetric_key = "< Enter the Group SAS token for your IoT Central application, found in Administration -> Device connection >"
model_id = "< Enter the model identity for the device model you would like the device identified with, found in Device templates -> select the device template -> select the model interface -> click 'View identity' >"
```

* device_id - The device identity for your device.  It does not already need to be registered with IoT Central.  For example: Device123

* scope_id -  The Scope identity for your IoT Central application you can find this in your IoT Central application in the Adminstrator -> Device Connection page
    ![Where to get scope id](https://github.com/iot-for-all/iot-central-batch-telemetry-with-python/blob/main/assets/scope_id.png)
* group_symmetric_key - The Group SAS token for your IoT Central application can be found in Administration -> Device connection
    ![Where to get group symmetric key](https://github.com/iot-for-all/iot-central-batch-telemetry-with-python/blob/main/assets/group_sas_key.png)
* model_id - The model identity for the device model you would like the device identified with, found in Device templates -> select the device template -> select the model interface -> click 'View identity'
    ![Where to get model id](https://github.com/iot-for-all/iot-central-batch-telemetry-with-python/blob/main/assets/model_id.png)

Then to run use:

```
python batch.py
```

or run from within your prefered IDE.
