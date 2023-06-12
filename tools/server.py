import zmq
from PIL import Image, ImageDraw, ImageFont
import time
import numpy as np

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://192.168.2.200:50003")

reorder_table = np.load("reorder_tables/moench03.npy")
inverse_table = np.argsort(reorder_table.flatten())
font = ImageFont.truetype("tools/RobotoMono-Regular.ttf", size=12)


def inverse_reorder(twod_array):
    return twod_array.flatten()[inverse_table]


def gen_bytes_frame(frameIndex):
    frame = np.zeros([400, 400], dtype=np.uint16)
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    # 13x13
    x = frameIndex // 15
    y = frameIndex % 15
    draw.text((y * 25, x * 25), str(frameIndex), font=font, fill=1)
    array = np.array(image).astype(np.uint16)
    return inverse_reorder(array).tobytes()


json_header = {
    "jsonversion": 4,
    "bitmode": 16,
    "fileIndex": 5,
    "detshape": [1, 1],
    "shape": [400, 400],
    "size": 320000,
    "acqIndex": 1,
    "frameIndex": 1,
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
    "frameIndex": 5,
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

while True:
    i = input(f"Enter amount of packets to send with 100Hz\n")
    for x in range(int(i)):
        json_header["frameIndex"] = x
        socket.send_json(json_header)
        socket.send(gen_bytes_frame(x))
        socket.send_json(dummy)
        print(f"Sent packet nr {x}")
        time.sleep(0.01)
