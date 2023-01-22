import zmq
import random
import sys
import time
import numpy as np

context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://127.0.0.1:5556")

c = 1
while True:
    a = np.ones([400 * 400], dtype=np.uint16)
    bytes = a.tobytes()
    c += 1
    i = input(f"Enter amount of packets to send with 100Hz\n")
    for x in range(int(i)):
        dict = {"frame": x}
        socket.send_json(dict)
        socket.send(bytes)
        print(f"Sent packet nr {x+1}")
        time.sleep(0.01)
