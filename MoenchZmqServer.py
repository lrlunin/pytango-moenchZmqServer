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

from tango.server import (
    run,
    attribute,
    command,
    Device,
    device_property,
    class_property,
)
from tango import GreenMode, AttrWriteType, DispLevel, AttrDataFormat
from multiprocessing.managers import SharedMemoryManager


class MoenchZmqServer(Device):
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
        access=AttrWriteType.READ_WRITE,
        hw_memorized=True,
        doc="cut-off value for thresholding",
    )

    counting_threshold = attribute(
        label="counting th",
        unit="ADU",
        dtype=float,
        access=AttrWriteType.READ_WRITE,
        hw_memorized=True,
        doc="cut-off value for counting",
    )
    processed_frames = attribute(
        label="proc frames",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="amount of already processed frames",
    )
    amount_frames = attribute(
        label="amount frames",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="expected frames to receive from detector",
    )
    server_running = attribute(
        display_level=DispLevel.EXPERT,
        label="is server running?",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
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
        self.shared_analog_img.value = value

    def read_analog_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_analog_img, flip=self.FLIP_IMAGE
        )

    def write_threshold_img(self, value):
        self.shared_threshold_img.value = value

    def read_threshold_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_threshold_img, flip=self.FLIP_IMAGE
        )

    def write_counting_img(self, value):
        self.shared_counting_img.value = value

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
            frame_index, array = await self.get_msg_pair()
            print(frame_index, array)
            future = self._process_pool.submit(
                processing_func,
                frame_index,
                array,
                self.shared_memory_analog_img,
                self._lock,
            )
            future = asyncio.wrap_future(future)

    async def get_msg_pair(self):
        isJSON = True
        array = np.zeros([400, 400], dtype=np.uint16)
        msg1 = await self._socket.recv()
        try:
            header = json.loads(msg1)
        except:
            isJSON = False
        if isJSON:
            msg2 = await self._socket.recv()
            array = np.frombuffer(msg2, dtype=np.uint16).reshape((400, 400))
        return header, array

    def _read_shared_array(self, shared_memory, flip: bool):
        array = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
        if flip:
            return np.flipud(array)
        else:
            return array

    @command
    def start_receiver(self):
        self.write_server_running(True)
        pass

    @command
    def stop_receiver(self):
        self.write_server_running(False)
        # self.save_files()

    @command
    def acquire_pedestals(self):
        pass

    def init_device(self):
        Device.init_device(self)
        self.get_device_properties(self.get_device_class())
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
        """
        Here is a small explanation why the threshold is handled in other way as images buffers:
        Despite the fact there is a thread safe "multiprocessing.Value" class for scalars (see above), there is no class for 2D array.
        Yes, there are 1D arrays available (see "multiprocessing.Array"), but they need to be handled as python arrays and not as numpy arrays.
        Continuos rearrangement of them into numpy arrays and vise versa considered as bad.
        In python 3.8 shared memory feature was introduced which allows to work directly with memory and use a numpy array as proxy to it.
        Documentation: https://docs.python.org/3.8/library/multiprocessing.shared_memory.html
        A good example: https://luis-sena.medium.com/sharing-big-numpy-arrays-across-python-processes-abf0dc2a0ab2

        tl;dr: we are able to share any numpy array between processes but in little other way
        """

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

    # updating of tango events for pictures buffers
    def update_images_events(self):
        self.push_change_event("analog_img")
        self.push_change_event("threshold_img")
        self.push_change_event("counting_img")

    # save files on disk for pictures buffers
    def save_files(self, path, filename, index):
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
def wrap_function(header, payload, lock, shared_memory, frame_func, *args, **kwargs):
    frame_processed = frame_func(payload)
    lock.acquire()
    img_buffer = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
    img_buffer += frame_processed
    lock.release()


# dummy processing function which increments the buffer
def processing_func(frame_index, array, shared_memory, lock):
    print(f"Enter processing frame {frame_index}")
    time.sleep(0.25)
    lock.acquire()
    buf_array = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
    print(f"begin shared value = {buf_array}")
    buf_array += 1
    lock.release()
    print(f"Left processing frame {frame_index}")


if __name__ == "__main__":
    run((MoenchZmqServer,))
