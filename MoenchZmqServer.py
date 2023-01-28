#!/home/moench/miniconda3/envs/pytango310/bin/python

import asyncio
import ctypes as cp
import json
import multiprocessing as mp
import os.path
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import shared_memory as sm
from multiprocessing.managers import SharedMemoryManager
import processing_functions

import numpy as np
from enum import IntEnum
import tango
import zmq
import zmq.asyncio
from PIL import Image
from tango import AttrDataFormat, AttrWriteType, DevState, DispLevel, GreenMode
from tango.server import (
    Device,
    attribute,
    command,
    device_property,
    run,
)


class ProcessingMode(IntEnum):
    ANALOG = 0
    THRESHOLD = 1
    COUNTING = 2
    PEDESTAL = 3


class MoenchZmqServer(Device):
    """Custom implementation of zmq processing server for X-ray detector MOENCH made in PSI which is integrated with a Tango device server."""

    processing_function = None
    processing_function_enum = ProcessingMode(0)

    _manager = None
    _context = None
    _socket = None
    _process_pool = None
    green_mode = GreenMode.Asyncio

    # probably should be rearranged in array, because there will pumped and unpumped images, for each type of processing
    # and further loaded with dynamic attributes
    shared_memory_pedestal = None
    shared_memory_analog_img = None
    shared_memory_threshold_img = None
    shared_memory_counting_img = None

    shared_threshold = None
    shared_counting_threshold = None
    shared_processed_frames = None
    shared_amount_frames = None
    shared_server_running = False
    reorder_table = None

    _save_analog_img = True
    _save_threshold_img = True
    _save_counting_img = True

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

    pedestal = attribute(
        display_level=DispLevel.EXPERT,
        label="pedestal",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ_WRITE,
        doc="pedestal (averaged dark images), i.e. offset which will be subtracted from each acquired picture",
    )
    analog_img = attribute(
        display_level=DispLevel.EXPERT,
        label="analog img",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ,
        doc="sum of images processed with subtracted pedestals",
    )
    threshold_img = attribute(
        display_level=DispLevel.EXPERT,
        label="threshold img",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ,
        doc='sum of "analog images" (with subtracted pedestal) processed with thresholding algorithm',
    )
    counting_img = attribute(
        display_level=DispLevel.EXPERT,
        label="counting img",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ,
        doc='sum of "analog images" (with subtracted pedestal) processed with counting algorithm',
    )

    threshold = attribute(
        label="th",
        unit="ADU",
        dtype=float,
        min_value=0.0,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="cut-off value for thresholding",
    )
    counting_threshold = attribute(
        label="counting th",
        unit="ADU",
        dtype=float,
        min_value=0.0,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="cut-off value for counting",
    )
    processing_mode = attribute(
        label="mode",
        dtype=ProcessingMode,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        fisallowed="isWriteAvailable",
        doc="mode of frames processing [ANALOG = 0, THRESHOLD = 1, COUNTING = 2]",
    )

    processed_frames = attribute(
        label="proc frames",
        dtype=int,
        access=AttrWriteType.READ,
        doc="amount of already processed frames",
    )
    amount_frames = attribute(
        label="expected frames",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="expected frames to receive from detector",
    )

    server_running = attribute(
        display_level=DispLevel.EXPERT,
        label="is server running?",
        dtype=bool,
        access=AttrWriteType.READ,
        doc="if true - server is running, otherwise - not",
    )

    save_analog_img = attribute(
        label="save analog",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="save analog .tiff file after acquisition",
    )

    save_threshold_img = attribute(
        label="save threshold",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="save threshold .tiff file after acquisition",
    )

    save_counting_img = attribute(
        label="save counting",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="save counting .tiff file after acquisition",
    )

    def write_pedestal(self, value):
        self.shared_pedestal.value = value

    def read_pedestal(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_pedestal, flip=self.FLIP_IMAGE
        )

    def write_analog_img(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_analog_img, value=value
        )

    def read_analog_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_analog_img, flip=self.FLIP_IMAGE
        )

    def write_threshold_img(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_threshold_img, value=value
        )

    def read_threshold_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_threshold_img, flip=self.FLIP_IMAGE
        )

    def write_counting_img(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_counting_img, value=value
        )

    def read_counting_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_counting_img, flip=self.FLIP_IMAGE
        )

    def write_threshold(self, value):
        self.shared_threshold.value = value

    def read_threshold(self):
        return self.shared_threshold.value

    def write_counting_threshold(self, value):
        self.shared_counting_threshold.value = value

    def read_counting_threshold(self):
        return self.shared_counting_threshold.value

    def write_processing_mode(self, value):
        # matching values and functions [ANALOG = 0, THRESHOLD = 1, COUNTING = 2]
        self.processing_function_enum = ProcessingMode(value)
        match self.processing_function_enum:
            case ProcessingMode.ANALOG:
                self.processing_function = processing_functions.analog
            case ProcessingMode.THRESHOLD:
                self.processing_function = processing_functions.thresholding
            case ProcessingMode.COUNTING:
                self.processing_function = processing_functions.counting

    def read_processing_mode(self):
        return self.processing_function_enum

    def write_processed_frames(self, value):
        self.shared_processed_frames.value = value

    def read_processed_frames(self):
        return self.shared_processed_frames.value

    def write_amount_frames(self, value):
        self.shared_amount_frames.value = value

    def read_amount_frames(self):
        return self.shared_amount_frames.value

    def write_server_running(self, value):
        self.shared_server_running.value = int(value)

    def read_server_running(self):
        return bool(self.shared_server_running.value)

    def write_save_analog_img(self, value):
        self._save_analog_img = value

    def read_save_analog_img(self):
        return self._save_analog_img

    def write_save_threshold_img(self, value):
        self._save_threshold_img = value

    def read_save_threshold_img(self):
        return self._save_threshold_img

    def write_save_counting_img(self, value):
        self._save_counting_img = value

    def read_save_counting_img(self):
        return self._save_counting_img

    # when processing is ready -> self.push_change_event(self, "analog_img"/"counting_img"/"threshold_img")

    async def main(self):
        while True:
            header, payload = await self.get_msg_pair()
            if payload is not None:
                # ANALOG = 0
                # THRESHOLD = 1
                # COUNTING = 2
                # PEDESTAL = 3
                # def wrap_function(
                # mode,
                # header,
                # payload,
                # lock,
                # shared_memories,
                # processed_frames,
                # amount_frames,
                # frame_func,
                # threshold,
                # counting_threshold,
                # *args,
                # **kwargs)

                future = self._process_pool.submit(
                    wrap_function,
                    self.processing_function_enum,
                    header,
                    payload.astype(float),
                    self._lock,
                    [
                        self.shared_memory_analog_img,
                        self.shared_memory_threshold_img,
                        self.shared_memory_counting_img,
                        self.shared_memory_pedestal,
                    ],  # need to changed corresponding to the frame_func
                    self.shared_processed_frames,
                    self.shared_amount_frames,
                    self.processing_function,
                    self.shared_threshold,
                    self.shared_counting_threshold,
                )
                future = asyncio.wrap_future(future)

    async def get_msg_pair(self):
        isNextPacketData = True
        header = None
        payload = None
        packet1 = await self._socket.recv()
        try:
            print("parsing header...")
            header = json.loads(packet1)
            print(header)
            isNextPacketData = header.get("data") == 1
            print(f"isNextPacketdata {isNextPacketData}")
        except:
            print("is not header")
            isNextPacketData = False
        if isNextPacketData:
            print("parsing data...")
            packet2 = await self._socket.recv()
            payload = np.zeros([400, 400], dtype=np.uint16)
            raw_buffer = np.frombuffer(packet2, dtype=np.uint16)
            # see in docs
            # should be moved to each process to prevent performance bottleneck
            payload = raw_buffer[self.reorder_table]
        return header, payload

    def _read_shared_array(self, shared_memory, flip: bool):
        self._lock.acquire()
        buf = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
        array = np.copy(buf)
        self._lock.release()
        if flip:
            return np.flipud(array)
        else:
            return array

    def _write_shared_array(self, shared_memory, value):
        self._lock.acquire()
        array = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
        array = value
        self._lock.release()

    @command
    def start_receiver(self):
        empty = np.zeros([400, 400], dtype=float)
        self.write_server_running(True)
        self.write_processed_frames(0)
        self.write_analog_img(empty)
        self.write_counting_img(empty)
        self.write_threshold_img(empty)
        self.set_state(DevState.RUNNING)

    @command
    def stop_receiver(self):
        self.write_server_running(False)
        self.set_state(DevState.ON)
        # self.save_files()

    @command
    def acquire_pedestals(self):
        pass

    def init_device(self):
        """Initial tangoDS setup"""
        Device.init_device(self)
        self.set_state(DevState.INIT)
        self.get_device_properties(self.get_device_class())

        self.reorder_table = np.load("reorder_table.npy")
        # sync manager for synchronization between threads
        self._manager = mp.Manager()
        # using simple mutex (lock) to synchronize
        self._lock = self._manager.Lock()

        # manager for allocation of shared memory between threads
        self._shared_memory_manager = SharedMemoryManager()
        # starting the shared memory manager
        self._shared_memory_manager.start()
        # default values of properties do not work without database though ¯\_(ツ)_/¯
        processing_cores_amount = 16  # self.PROCESSING_CORES
        zmq_ip = self.ZMQ_RX_IP
        zmq_port = self.ZMQ_RX_PORT

        # using shared threadsafe Value instance from multiprocessing
        self.shared_threshold = self._manager.Value("f", 0)
        self.shared_counting_threshold = self._manager.Value("f", 0)
        self.shared_server_running = self._manager.Value("b", 0)
        self.shared_processed_frames = self._manager.Value("I", 0)
        self.shared_amount_frames = self._manager.Value("I", 0)
        # calculating how many bytes need to be allocated and shared for a 400x400 float numpy array
        img_bytes = np.zeros([400, 400], dtype=float).nbytes
        # allocating 4 arrays of this type
        self.shared_memory_pedestal = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_analog_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_threshold_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_counting_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        # creating thread pool executor to which the frame processing will be assigned
        self._process_pool = ProcessPoolExecutor(processing_cores_amount)

        # creating and initialing socket to read from
        self._init_zmq_socket(zmq_ip, zmq_port)
        loop = asyncio.get_event_loop()
        loop.create_task(self.main())

        # initialization of tango events for pictures buffers
        self.set_change_event("analog_img", True, False)
        self.set_change_event("threshold_img", True, False)
        self.set_change_event("counting_img", True, False)
        self.set_state(DevState.ON)

    # updating of tango events for pictures buffers
    @command
    def update_images_events(self):
        self.push_change_event("analog_img", self.read_analog_img(), 400, 400),
        self.push_change_event("threshold_img", self.read_threshold_img(), 400, 400)
        self.push_change_event("counting_img", self.read_counting_img(), 400, 400)

    # save files on disk for pictures buffers
    def save_files(self, path, filename, index):
        """Function for saving the buffered images in .tiff format.
        The files will have different postfixes depending on processing mode.

        Args:
            path (str): folder to save
            filename (str): name to save
            index (str): capture index
        """
        savepath = os.path.join(path, filename)
        if self.read_save_analog_img():
            im = Image.fromarray(self.read_analog_img())
            im.save(f"{savepath}_{index}_analog.tiff")

        if self.read_save_threshold_img():
            im = Image.fromarray(self.read_threshold_img())
            im.save(f"{savepath}_{index}_threshold_{self.read_threshold()}.tiff")

        if self.read_save_counting_img():
            im = Image.fromarray(self.read_analog_img())
            im.save(
                f"{savepath}_{index}_counting_{self.read_counting_threshold()}.tiff"
            )

    def _init_zmq_socket(self, zmq_ip: str, zmq_port: str):
        endpoint = f"tcp://{zmq_ip}:{zmq_port}"
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        print(f"Connecting to: {endpoint}")
        self._socket.connect(endpoint)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")

    def delete_device(self):
        self._process_pool.shutdown()
        self._manager.shutdown()
        self._shared_memory_manager.shutdown()


# concept for the future decorator to isolate concurrency and tango features from evaluation logic hidden in frame_func
def wrap_function(
    mode,
    header,
    payload,
    lock,
    shared_memories,
    processed_frames,
    amount_frames,
    frame_func,
    threshold,
    counting_threshold,
    *args,
    **kwargs,
):
    """Decorator to wrap any processing function applied for a single frame

    Args:
        header (dict): JSON formatted header from the detector
        payload (np.array): np.array formatted single frame from the detector
        lock (multiprocessing.Lock): lock (mutex) to provide synchronization for shared memory access
        shared_memory (shared_memory.SharedMemory): shared memory instance for image buffer
        processed_frames (multiprocessing.Value): shared value instance to increment to track how many frames were processed
        amount_frames (multiprocessing.Value): shared value instance with amount of frames to expect
        frame_func (function): any function with following signature: function(frame : np.array, dark : np.array, *args, **kwargs) -> result : np.array"
    """
    frame_index = header.get("frameIndex")
    shared_memory = None
    pedestal = np.ndarray((400, 400), dtype=float, buffer=shared_memories[3].buf)
    match mode:
        case ProcessingMode.ANALOG:
            shared_memory = shared_memories[0]
        case ProcessingMode.THRESHOLD:
            shared_memory = shared_memories[1]
        case ProcessingMode.COUNTING:
            shared_memory = shared_memories[2]
        case ProcessingMode.PEDESTAL:
            shared_memory = shared_memories[3]

    # frame_processed = frame_func(payload)
    lock.acquire()
    print(f"Enter processing frame {frame_index}")
    img_buffer = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
    match mode:
        case ProcessingMode.ANALOG:
            payload -= pedestal
            img_buffer += payload
        case ProcessingMode.THRESHOLD:
            payload -= pedestal
            img_buffer += payload > threshold
        case ProcessingMode.COUNTING:
            pass
        case ProcessingMode.PEDESTAL:
            img_buffer += payload / amount_frames
    print(f"Left processing frame {frame_index}")

    processed_frames.value += 1
    print(f"Processed frames {processed_frames.value}/{amount_frames.value}")
    if processed_frames.value == amount_frames.value:
        print('All frames processed => call "stop receiver procedure"')
    lock.release()


if __name__ == "__main__":
    run((MoenchZmqServer,))
