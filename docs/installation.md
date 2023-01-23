## Dependencies
* python 3.10
* pyzmq
* pytango
* Pillow
* scipy
* skicit-image

!!! warning
    python3.8 is broken

!!! note
    python3.10 works though

## Inital setup
tango ds properties table:

```python
ZMQ_RX_IP = device_property(
    dtype=str,
    doc="port of the slsReceiver instance, must match the config",
    default_value="192.168.2.200",
)

ZMQ_RX_PORT = device_property(
    dtype=str,
    doc="ip of slsReceiver instance, must match the config",
    default_value="50003",
)

PROCESSING_CORES = device_property(
    dtype=int,
    doc="cores amount to process, up to 72 on MOENCH workstation",
    default_value=20,
)
FLIP_IMAGE = device_property(
    dtype=bool,
    doc="should the final image be flipped/inverted along y-axis",
    default_value=True,
)
```

