import zmq
import random
import sys
import time
import numpy as np

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://127.0.0.1:50003")

raw_frame_sim = np.zeros([400, 400], dtype=np.uint16)
c = 0
for y in range(0, 400, 100):
    for x in range(0, 400):
        raw_frame_sim[y : y + 100, x] = c
        c += 1

# raw_frame_sim = np.arange(0, 400 * 400, dtype=np.uint16).reshape(400, 400)

json_header = {
    "jsonversion": 4,
    "bitmode": 16,
    "fileIndex": 6,
    "detshape": [1, 1],
    "shape": [400, 400],
    "size": 320000,
    "acqIndex": 1,
    "frameIndex": 0,
    "progress": 100.0,
    "fname": "/mnt/LocalData/DATA/MOENCH/20230128_run/230128",
    "data": 1,
    "completeImage": 1,
    "frameNumber": 1,
    "expLength": 0,
    "packetNumber": 40,
    "bunchId": 0,
    "timestamp": 0,
    "modId": 0,
    "row": 0,
    "column": 0,
    "reserved": 0,
    "debug": 0,
    "roundRNumber": 0,
    "detType": 5,
    "version": 1,
    "flipRows": 0,
    "quad": 0,
    "addJsonHeader": {"detectorMode": "analog", "frameMode": "raw"},
}

dummy = {
    "jsonversion": 4,
    "bitmode": 0,
    "fileIndex": 0,
    "detshape": [0, 0],
    "shape": [0, 0],
    "size": 0,
    "acqIndex": 0,
    "frameIndex": 0,
    "progress": 0.0,
    "fname": "",
    "data": 0,
    "completeImage": 0,
    "frameNumber": 0,
    "expLength": 0,
    "packetNumber": 0,
    "bunchId": 0,
    "timestamp": 0,
    "modId": 0,
    "row": 0,
    "column": 0,
    "reserved": 0,
    "debug": 0,
    "roundRNumber": 0,
    "detType": 0,
    "version": 0,
    "flipRows": 0,
    "quad": 0,
}
c = 1
while True:
    a = raw_frame_sim
    bytes = a.tobytes()
    c += 1
    i = input(f"Enter amount of packets to send with 100Hz\n")
    for x in range(int(i)):
        socket.send_json(json_header)
        socket.send(bytes)
        socket.send_json(dummy)
        print(f"Sent packet nr {x+1}")
        time.sleep(0.01)
