## Dependencies
* python >3.10
* pyzmq
* tornado
* pytango
* Pillow
* scipy
* skicit-image

!!! warning
    Please note that this TangoDS explicitly uses `asyncio` API firstly introduced in python 3.8. However, there are several bugs in the python 3.8 which do not allow to use this TangoDS properly. These bugs were fixed in the version 3.10 of python. Since this version is required some python 3.10 specific features were used in the code.

!!! note
    python3.10 works though

## Initial setup
To use this TangoDS you need to firstly register it in your Tango database. One of options is to [use Jive](https://tango-controls.readthedocs.io/en/latest/tutorials-and-howtos/how-tos/how-to-start-device-server.html?highlight=Server%20Wizard#starting-device-servers-with-jive).

The following TangoDS properties should be specified: 

| Property name      | Datatype  | Description                                                                                                                                                                                                                                                                    | Default value                                          |
| ------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `ZMQ_RX_IP`        | `String`  | IP address where the detector opens ZMQ socket, must match the detector's config                                                                                                                                                                                               | `"192.168.2.200"` (workstation's IP on 10Gb interface) |
| `ZMQ_RX_PORT`      | `String`  | Port where the detector opens ZMQ socket, must match the detector's config                                                                                                                                                                                                     | `"50003"`                                              |
| `PROCESSING_CORES` | `Integer` | Amount of cores utilized/processes spawned for parallel processing of oncoming images                                                                                                                                                                                          | `20`                                                   |
| `FLIP_IMAGE`       | `Boolean` | Flip the stored images in the `read_` functions of the TangoDS. Due to the other specification used for detector the oncoming image from the detector is flipped vertically. Please note that the images are stored in unflipped state and will be flipped only while reading. | `true`                                                 |


