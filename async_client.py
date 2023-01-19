import zmq
import numpy as np
import time
import zmq.asyncio
import json
import asyncio
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import ctypes as cp

def processing_func(frame_index, array, shared_value):
    print(f'Enter processing frame {frame_index}')
    time.sleep(0.25)
    shared_value.value += frame_index
    print(f'Left processing frame {frame_index}')
    print(f'shared value = {shared_value.value}')

async def main():
    pool = ProcessPoolExecutor(16)
    with mp.Manager() as manager:
        shared_value = manager.Value(cp.c_int16, 0)
        while True:
            frame_index, array = await get_msg_pair()
            print(frame_index ,array)
            future = pool.submit(processing_func, frame_index, array, shared_value)
            future = asyncio.wrap_future(future)
        
async def get_msg_pair():
    msg1, msg2 = await socket.recv(), await socket.recv()
    header = json.loads(msg1).get("frame")
    array = np.frombuffer(msg2, dtype = np.uint16).reshape((400,400)).sum()
    return header, array

if __name__ == '__main__':
    endpoint = "tcp://127.0.0.1:5556"
    ctx = zmq.asyncio.Context()
    socket = ctx.socket(zmq.SUB)
    print(f"Connecting to: {endpoint}")
    socket.connect(endpoint)
    socket.setsockopt(zmq.SUBSCRIBE, b'')
    asyncio.run(main())