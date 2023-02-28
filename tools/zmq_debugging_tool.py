import zmq
import numpy as np
import time
import zmq.asyncio
import os.path
import json
import asyncio
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from multiprocessing import shared_memory as sm
import ctypes as cp
from PIL import Image


async def main():
    endpoint = f"tcp://192.168.2.200:50003"
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    print(f"Connecting to: {endpoint}")
    socket.connect(endpoint)
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    isNextdata = False
    while True:
        msg = await socket.recv()
        readout = 0
        try:
            readout = json.loads(msg)
            isNextdata = readout.get("data") == 1
        except:
            print("Could not parse JSON, trying to prase numpy...")
            try:
                if isNextdata:
                    print(f"Next data was: {isNextdata}, reading payload")
                    readout = np.frombuffer(msg, dtype=np.uint16).shape
                else:
                    print("Next data was false, do nothing")
            except:
                print("Could not parse numpy array either")
        print(readout)


if __name__ == "__main__":
    asyncio.run(main())
