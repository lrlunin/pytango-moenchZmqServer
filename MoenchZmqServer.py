#!/home/moench/miniconda3/envs/pytango310/bin/python

import asyncio
import ctypes as cp
import json
import multiprocessing as mp
from os import path, makedirs, listdir
import time
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import shared_memory as sm
from multiprocessing.managers import SharedMemoryManager
import processing_functions

import re
import numpy as np
from enum import IntEnum
import tango
import zmq
import zmq.asyncio
from PIL import Image
from tango import AttrDataFormat, AttrWriteType, DevState, DispLevel, GreenMode, Except
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
    _processing_function_enum = ProcessingMode(0)

    _manager = None
    _context = None
    _socket = None
    _process_pool = None
    green_mode = GreenMode.Asyncio

    # probably should be rearranged in array, because there will pumped and unpumped images, for each type of processing
    # and further loaded with dynamic attributes
    shared_memory_pedestal = None

    shared_memory_analog_img = None
    shared_memory_analog_img_pumped = None

    shared_memory_threshold_img = None
    shared_memory_threshold_img_pumped = None

    shared_memory_counting_img = None
    shared_memory_counting_img_pumped = None

    shared_memory_raw_img = None

    shared_memory_single_frames = None
    max_frame_index = None

    # shared scalar values
    shared_threshold = None
    shared_counting_threshold = None
    shared_processed_frames = None
    shared_received_frames = None
    shared_receive_frames = None
    _split_pump = False
    _process_pedestal_img = False
    _process_analog_img = True
    _process_threshold_img = True
    _process_counting_img = False

    # reorder table for frame
    reorder_table = None

    _save_analog_img = True
    _save_threshold_img = True
    _save_counting_img = True

    _filename = ""
    _filepath = ""
    _file_index = 0

    _abort_await = False

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
    SAVE_ROOT_PATH = device_property(
        dtype=str,
        doc="folder to save in",
        default_value="/mnt/LocalData/DATA/MOENCH",
    )
    SINGLE_FRAME_BUFFER_SIZE = device_property(
        dtype=int, doc="how much single frames can be stored", default_value=10000
    )

    filename = attribute(
        label="filename",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="File prefix",
    )
    filepath = attribute(
        label="filepath",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        doc="dir where data files will be written",
    )
    file_index = attribute(
        label="next file index",
        dtype=int,
        access=AttrWriteType.READ_WRITE,
        doc="File name: [filename]_d0_f[sub_file_index]_[acquisition/file_index].raw",
    )
    previous_file_index = attribute(
        label="previous file index",
        dtype=int,
        access=AttrWriteType.READ,
        doc="File name: [filename]_d0_f[sub_file_index]_[acquisition/file_index].raw",
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
    analog_img_pumped = attribute(
        display_level=DispLevel.EXPERT,
        label="analog img pumped",
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
    threshold_img_pumped = attribute(
        display_level=DispLevel.EXPERT,
        label="threshold img pumped",
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
    counting_img_pumped = attribute(
        display_level=DispLevel.EXPERT,
        label="counting img pumped",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ,
        doc='sum of "analog images" (with subtracted pedestal) processed with counting algorithm',
    )
    raw_img = attribute(
        display_level=DispLevel.EXPERT,
        label="raw img",
        dtype=float,
        dformat=AttrDataFormat.IMAGE,
        max_dim_x=400,
        max_dim_y=400,
        access=AttrWriteType.READ,
        doc="sum of all frames without pedestal subtraction",
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
    # processing_mode = attribute(
    #     label="mode",
    #     dtype=ProcessingMode,
    #     access=AttrWriteType.READ_WRITE,
    #     memorized=True,
    #     hw_memorized=True,
    #     doc="mode of frames processing [ANALOG = 0, THRESHOLD = 1, COUNTING = 2, PEDESTAL = 3]",
    # )

    processed_frames = attribute(
        label="proc frames",
        dtype=int,
        access=AttrWriteType.READ,
        doc="amount of already processed frames",
    )
    received_frames = attribute(
        label="received frames",
        dtype=int,
        access=AttrWriteType.READ,
        doc="expected frames to receive from detector",
    )

    receive_frames = attribute(
        display_level=DispLevel.EXPERT,
        label="receive frames?",
        dtype=bool,
        access=AttrWriteType.READ,
        doc="if true - server receives frames, otherwise - ignores",
    )

    split_pump = attribute(
        label="split (un)pumped",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="split odd and even frames",
    )

    process_pedestal_img = attribute(
        label="process pedestal",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="use this acquisition series as pedestal",
    )

    process_analog_img = attribute(
        label="process analog",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="process analog while acquisition",
    )

    process_threshold_img = attribute(
        label="process threshold",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="process threshold while acquisition",
    )

    process_counting_img = attribute(
        label="process counting",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="process counting while acquisition",
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

    def write_filename(self, value):
        self._filename = value

    def read_filename(self):
        return self._filename

    def write_filepath(self, folders):
        root_path = self.SAVE_ROOT_PATH
        joined_path = path.join(root_path, folders)
        if not path.isdir(joined_path):
            try:
                makedirs(joined_path)
            except OSError:
                Except.throw_exception(
                    "Cannot create directory!",
                    f"no permissions to create dir {joined_path}",
                    "write_filepath",
                )
        self._filepath = joined_path

    def read_filepath(self):
        return self._filepath

    def write_file_index(self, value):
        self._file_index = value

    def read_file_index(self):
        return self._file_index

    def write_previous_file_index(self, value):
        pass

    def read_previous_file_index(self):
        return self.read_file_index() - 1

    def write_pedestal(self, value):
        self._write_shared_array(shared_memory=self.shared_memory_pedestal, value=value)

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

    def write_analog_img_pumped(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_analog_img_pumped, value=value
        )

    def read_analog_img_pumped(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_analog_img_pumped, flip=self.FLIP_IMAGE
        )

    def write_threshold_img(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_threshold_img, value=value
        )

    def read_threshold_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_threshold_img, flip=self.FLIP_IMAGE
        )

    def write_threshold_img_pumped(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_threshold_img_pumped, value=value
        )

    def read_threshold_img_pumped(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_threshold_img_pumped, flip=self.FLIP_IMAGE
        )

    def write_counting_img(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_counting_img, value=value
        )

    def read_counting_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_counting_img, flip=self.FLIP_IMAGE
        )

    def write_counting_img_pumped(self, value):
        self._write_shared_array(
            shared_memory=self.shared_memory_counting_img_pumped, value=value
        )

    def read_counting_img_pumped(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_counting_img_pumped, flip=self.FLIP_IMAGE
        )

    def write_raw_img(self, value):
        self._write_shared_array(shared_memory=self.shared_memory_raw_img, value=value)

    def read_raw_img(self):
        return self._read_shared_array(
            shared_memory=self.shared_memory_raw_img, flip=self.FLIP_IMAGE
        )

    def write_threshold(self, value):
        # with self.shared_threshold.get_lock():
        self.shared_threshold.value = value

    def read_threshold(self):
        return self.shared_threshold.value

    def write_counting_threshold(self, value):
        # with self.shared_counting_threshold.get_lock():
        self.shared_counting_threshold.value = value

    def read_counting_threshold(self):
        return self.shared_counting_threshold.value

    def write_processing_mode(self, value):
        # matching values and functions [ANALOG = 0, THRESHOLD = 1, COUNTING = 2]
        self._processing_function_enum = ProcessingMode(value)
        # will be
        # match self.processing_function_enum:
        #     case ProcessingMode.ANALOG:
        #         self.processing_function = processing_functions.analog
        #     case ProcessingMode.THRESHOLD:
        #         self.processing_function = processing_functions.thresholding
        #     case ProcessingMode.COUNTING:
        #         self.processing_function = processing_functions.counting

    def read_processing_mode(self):
        return self._processing_function_enum

    def write_processed_frames(self, value):
        # with self.shared_processed_frame.get_lock():
        self.shared_processed_frames.value = value

    def read_processed_frames(self):
        return self.shared_processed_frames.value

    def write_received_frames(self, value):
        # with self.shared_received_frames.get_lock():
        self.shared_received_frames.value = value

    def read_received_frames(self):
        return self.shared_received_frames.value

    def write_receive_frames(self, value):
        self.shared_receive_frames.value = int(value)

    def read_receive_frames(self):
        return bool(self.shared_receive_frames.value)

    def write_split_pump(self, value):
        self._split_pump = bool(value)

    def read_split_pump(self):
        return self._split_pump

    def write_process_pedestal_img(self, value):
        self._process_pedestal_img = value

    def read_process_pedestal_img(self):
        return self._process_pedestal_img

    def write_process_analog_img(self, value):
        self._process_analog_img = value

    def read_process_analog_img(self):
        return self._process_analog_img

    def write_process_threshold_img(self, value):
        self._process_threshold_img = value

    def read_process_threshold_img(self):
        return self._process_threshold_img

    def write_process_counting_img(self, value):
        self._process_counting_img = value

    def read_process_counting_img(self):
        return self._process_counting_img

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
            if payload is not None and self.read_receive_frames():
                # received frames increment only in case the frame is not corrupted (reshaping is on)
                self.shared_received_frames.value += 1
                # see in docs
                # should be moved to each process to prevent performance bottleneck
                future = self._process_pool.submit(
                    wrap_function,
                    self.shared_memory_single_frames,
                    self.max_frame_index,
                    [
                        self.read_process_pedestal_img(),
                        self.read_process_analog_img(),
                        self.read_process_threshold_img(),
                        self.read_process_counting_img(),
                    ],
                    header,
                    payload,
                    self._lock,
                    [
                        self.shared_memory_analog_img,
                        self.shared_memory_analog_img_pumped,
                        self.shared_memory_threshold_img,
                        self.shared_memory_threshold_img_pumped,
                        self.shared_memory_counting_img,
                        self.shared_memory_counting_img_pumped,
                        self.shared_memory_pedestal,
                        self.shared_memory_raw_img,
                    ],  # need to changed corresponding to the frame_func
                    self.shared_processed_frames,
                    self.shared_threshold,
                    self.shared_counting_threshold,
                    self.read_split_pump(),
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
            raw_buffer = np.frombuffer(packet2, dtype=np.uint16)
            try:
                payload = raw_buffer[self.reorder_table]
            except:
                frameIndex = header.get("frameIndex")
                print(f"Reorder of frame {frameIndex} failed. Ignored...")
        return header, payload

    def _read_shared_array(self, shared_memory, flip: bool):
        # comes to dead lock if using lock
        # self._lock.acquire()
        buf = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
        array = np.copy(buf)
        # self._lock.release()
        if flip:
            return np.flipud(array)
        else:
            return array

    def _write_shared_array(self, shared_memory, value):
        # do not work
        # self._lock.acquire()
        array = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
        array[:] = value[:]
        # self._lock.release()

    def _empty_shared_array(self, shared_value):
        array = np.ndarray((400, 400), dtype=float, buffer=shared_value.buf)
        array[:] = np.zeros_like(array)

    @command
    def start_receiver(self):
        empty = np.zeros([400, 400], dtype=float)
        # clear previous values
        if self.read_processing_mode() is ProcessingMode.PEDESTAL:
            self._empty_shared_array(self.shared_memory_pedestal)
        self.write_processed_frames(0)
        self.write_received_frames(0)
        self.max_frame_index.value = 0

        self._empty_shared_array(self.shared_memory_single_frames)
        self._empty_shared_array(self.shared_memory_analog_img)
        self._empty_shared_array(self.shared_memory_analog_img_pumped)
        self._empty_shared_array(self.shared_memory_threshold_img)
        self._empty_shared_array(self.shared_memory_threshold_img_pumped)
        self._empty_shared_array(self.shared_memory_counting_img)
        self._empty_shared_array(self.shared_memory_counting_img_pumped)
        self._empty_shared_array(self.shared_memory_raw_img)
        self.write_receive_frames(True)
        self.set_state(DevState.RUNNING)

    async def async_stop_receiver(self, received_frames):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.block_stop_receiver, received_frames)

    def block_stop_receiver(self, received_frames_at_the_time):
        self.write_receive_frames(False)
        while (
            self.shared_processed_frames.value < received_frames_at_the_time
            and not self._abort_await
        ):
            print(f"abort wait: {self._abort_await}")
            time.sleep(0.5)
        # averaging pedetal which we have accumulated
        self._abort_await = False
        if self.read_process_pedestal_img():
            non_averaged_pedestal = self._read_shared_array(
                self.shared_memory_pedestal, flip=False
            )
            averaged_pedesal = non_averaged_pedestal / received_frames_at_the_time
            self.write_pedestal(averaged_pedesal)
        # HERE ALL POST HOOKS
        self.update_images_events()
        self.save_files()
        index = self.read_file_index()
        self.write_file_index(index + 1)
        self.set_state(DevState.ON)

    @command
    async def stop_receiver(self):
        received_frames = self.shared_received_frames.value
        print(f"received {received_frames} frames")
        loop = asyncio.get_event_loop()
        loop.create_task(self.async_stop_receiver(received_frames))

    @command
    def abort_receiver(self):
        self._abort_await = True

    @command
    def reset_pedestal(self):
        empty = np.zeros([400, 400], dtype=float)
        self.write_pedestal(empty)

    def get_max_file_index(self, filepath, filename):
        # full_file_name_like = 202301031_run_5_.....tiff
        # get list of files in the directory
        file_list = listdir(filepath)

        # getting files which begin with the same filename
        captures_list = list(
            filter(lambda file_name: file_name.startswith(filename), file_list)
        )
        # if there is no files with this filename -> 0
        if len(captures_list) == 0:
            return 0
        # if there is any file with the same filename
        else:
            # finding index with regexp while index is a decimal number which stays after "filename_"
            # (\d*) - is an indented group 1
            r = re.compile(rf"^{filename}_(\d*)")
            # regex objects which match the upper statement
            reg = map(r.search, captures_list)
            # getting max from the group 1 <=> index
            max_index = max(list(map(lambda match: int(match.group(1)), reg)))
            return max_index

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

        processing_cores_amount = self.PROCESSING_CORES
        zmq_ip = self.ZMQ_RX_IP
        zmq_port = self.ZMQ_RX_PORT

        # creating default values for folders, filename and check index
        # formatting date like 20230131
        date_formatted = datetime.today().strftime("%Y%m%d")
        self.write_filepath(f"{date_formatted}_run")
        self.write_filename(f"{date_formatted}_run")
        max_file_index = self.get_max_file_index(
            self.read_filepath(), self.read_filename()
        )
        self.write_file_index(max_file_index + 1)

        # using shared thread-safe Value instance from multiprocessing
        self.shared_threshold = self._manager.Value("f", 0)
        self.shared_counting_threshold = self._manager.Value("f", 0)
        self.shared_receive_frames = self._manager.Value("b", 0)
        self.shared_processed_frames = self._manager.Value("I", 0)
        self.shared_received_frames = self._manager.Value("I", 0)
        self.shared_amount_frames = self._manager.Value("I", 0)
        self.shared_split_pump = self._manager.Value("b", 0)

        self.max_frame_index = self._manager.Value("I", 0)

        # calculating how many bytes need to be allocated and shared for a 400x400 float numpy array
        img_bytes = np.zeros([400, 400], dtype=float).nbytes
        # allocating 4 arrays of this type
        self.shared_memory_pedestal = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_analog_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_analog_img_pumped = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_threshold_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_threshold_img_pumped = (
            self._shared_memory_manager.SharedMemory(size=img_bytes)
        )
        self.shared_memory_counting_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )
        self.shared_memory_counting_img_pumped = (
            self._shared_memory_manager.SharedMemory(size=img_bytes)
        )

        self.shared_memory_raw_img = self._shared_memory_manager.SharedMemory(
            size=img_bytes
        )

        buffer_bytes = np.zeros([10000, 400, 400], dtype=np.uint16).nbytes

        self.shared_memory_single_frames = self._shared_memory_manager.SharedMemory(
            size=buffer_bytes
        )
        # creating thread pool executor to which the frame processing will be assigned
        self._process_pool = ProcessPoolExecutor(processing_cores_amount)

        # creating and initialing socket to read from
        self._init_zmq_socket(zmq_ip, zmq_port)
        loop = asyncio.get_event_loop()
        loop.create_task(self.main())

        # assigning the previews for the images (just for fun)
        self._write_shared_array(
            self.shared_memory_analog_img, np.load("default_images/analog_unpumped.npy")
        )
        self._write_shared_array(
            self.shared_memory_analog_img_pumped,
            np.load("default_images/analog_pumped.npy"),
        )
        self._write_shared_array(
            self.shared_memory_threshold_img,
            np.load("default_images/threshold_unpumped.npy"),
        )
        self._write_shared_array(
            self.shared_memory_threshold_img_pumped,
            np.load("default_images/threshold_pumped.npy"),
        )
        self._write_shared_array(
            self.shared_memory_counting_img,
            np.load("default_images/counting_unpumped.npy"),
        )
        self._write_shared_array(
            self.shared_memory_counting_img_pumped,
            np.load("default_images/counting_pumped.npy"),
        )

        # initialization of tango events for pictures buffers
        self.set_change_event("analog_img", True, False)
        self.set_change_event("threshold_img", True, False)
        self.set_change_event("counting_img", True, False)
        self.set_change_event("analog_img_pumped", True, False)
        self.set_change_event("threshold_img_pumped", True, False)
        self.set_change_event("counting_img_pumped", True, False)
        self.set_state(DevState.ON)

    # updating of tango events for pictures buffers
    @command
    def update_images_events(self):
        self.push_change_event("analog_img", self.read_analog_img(), 400, 400),
        self.push_change_event("threshold_img", self.read_threshold_img(), 400, 400)
        self.push_change_event("counting_img", self.read_counting_img(), 400, 400)
        self.push_change_event(
            "analog_img_pumped", self.read_analog_img_pumped(), 400, 400
        ),
        self.push_change_event(
            "threshold_img_pumped", self.read_threshold_img_pumped(), 400, 400
        )
        self.push_change_event(
            "counting_img_pumped", self.read_counting_img_pumped(), 400, 400
        )
        self.push_change_event("raw_img", self.read_raw_img(), 400, 400)

    # save files on disk for pictures buffers
    def save_files(self):
        """Function for saving the buffered images in .tiff format.
        The files will have different postfixes depending on processing mode.

        Args:
            path (str): folder to save
            filename (str): name to save
            index (str): capture index
        """
        filepath = self.read_filepath()
        filename = self.read_filename()
        index = self.read_file_index()
        # need to be refactored soon
        savepath = path.join(filepath, filename)
        time_str = datetime.now().strftime("%H:%M:%S")

        if self.read_process_pedestal_img():
            im = Image.fromarray(self.read_pedestal())
            full_path_pedestal = f"{savepath}_{index}_pedestal"
            if path.isfile(f"{full_path_pedestal}.tiff"):
                full_path_pedestal += f"_{time_str}"
            im.save(f"{full_path_pedestal}.tiff")
        else:
            if self.read_process_analog_img() and self.read_save_analog_img():
                im = Image.fromarray(self.read_analog_img())
                full_path_unpumped = f"{savepath}_{index}_analog"

                if path.isfile(f"{full_path_unpumped}.tiff"):
                    full_path_unpumped += f"_{time_str}"
                im.save(f"{full_path_unpumped}.tiff")
                if self.read_split_pump():
                    im_pumped = Image.fromarray(self.read_analog_img_pumped())
                    full_path_pumped = f"{savepath}_{index}_analog_pumped"
                    if path.isfile(f"{full_path_pumped}.tiff"):
                        full_path_pumped += f"_{time_str}"
                    im_pumped.save(f"{full_path_pumped}.tiff")

            if self.read_process_threshold_img() and self.read_save_threshold_img():
                threshold = self.read_threshold()
                im = Image.fromarray(self.read_threshold_img())
                full_path_unpumped = f"{savepath}_{index}_threshold_{threshold}"
                if path.isfile(f"{full_path_unpumped}.tiff"):
                    full_path_unpumped += f"_{time_str}"
                im.save(f"{full_path_unpumped}.tiff")
                if self.read_split_pump():
                    im_pumped = Image.fromarray(self.read_threshold_img_pumped())
                    full_path_pumped = (
                        f"{savepath}_{index}_threshold_{threshold}_pumped"
                    )
                    if path.isfile(f"{full_path_pumped}.tiff"):
                        full_path_pumped += f"_{time_str}"
                    im_pumped.save(f"{full_path_pumped}.tiff")

        single_frames = np.ndarray(
            (10000, 400, 400),
            dtype=np.uint16,
            buffer=self.shared_memory_single_frames.buf,
        )
        single_frames_shorten = single_frames[: self.max_frame_index.value + 1]
        single_frames_filename = f"{savepath}_{index}"
        if path.isfile(f"{single_frames_filename}.npy"):
            single_frames_filename += f"_{time_str}"
        np.save(f"{single_frames_filename}.npy", single_frames_shorten)
        # if self.read_save_counting_img():
        #     im = Image.fromarray(self.read_analog_img())
        #     im.save(
        #         f"{savepath}_{index}_counting_{self.read_counting_threshold()}.tiff"
        #     )

    def _init_zmq_socket(self, zmq_ip: str, zmq_port: str):
        endpoint = f"tcp://{zmq_ip}:{zmq_port}"
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        print(f"Connecting to: {endpoint}")
        self._socket.connect(endpoint)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")
        hwm = self._socket.get_hwm()
        print(f"HWM of the socket = {hwm}")

    def delete_device(self):
        self._process_pool.shutdown()
        self._manager.shutdown()
        self._shared_memory_manager.shutdown()


def wrap_function(
    buffer_shared_memory,
    max_file_index,
    use_modes,
    header,
    payload,
    lock,
    shared_memories,
    processed_frames,
    threshold,
    counting_threshold,
    split_pump,
):
    # use_modes = [self.read_process_pedestal_img(),  self.read_process_analog_img(), self.read_process_threshold_img(), self.read_process_counting_img()]
    # [
    #     shared_memory_analog_img,
    #     shared_memory_analog_img_pumped,
    #     shared_memory_threshold_img,
    #     shared_memory_threshold_img_pumped,
    #     shared_memory_counting_img,
    #     shared_memory_counting_img_pumped,
    #     shared_memory_pedestal,
    # ]
    frame_index = header.get("frameIndex")

    process_pedestal, process_analog, process_threshold, process_counting = use_modes
    print(use_modes)

    analog_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[0].buf)
    analog_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[1].buf
    )
    threshold_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[2].buf)
    threshold_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[3].buf
    )
    counting_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[4].buf)
    counting_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[5].buf
    )
    pedestal = np.ndarray((400, 400), dtype=float, buffer=shared_memories[6].buf)

    raw = np.ndarray((400, 400), dtype=float, buffer=shared_memories[7].buf)

    single_frame_buffer = np.ndarray(
        (10000, 400, 400), dtype=np.uint16, buffer=buffer_shared_memory.buf
    )
    lock.acquire()
    max_file_index.value = max(max_file_index.value, frame_index)
    single_frame_buffer[frame_index] = payload
    payload_copy = payload.astype(float, copy=True)
    no_ped = payload_copy - pedestal
    print(f"Enter processing frame {frame_index}")

    raw += payload
    if process_pedestal:
        # just summing up because amount of successfully received frames is unknown
        # they will be averaged in stop_server post hook
        pedestal += payload_copy
    else:
        if process_analog:
            print("Processing analog...")
            if split_pump:
                if frame_index % 2 == 0:
                    analog_img += no_ped
                else:
                    analog_img_pumped += no_ped
            else:
                analog_img += no_ped
        if process_threshold:
            print("Processing threshold...")
            thresholded = no_ped > threshold.value
            print(f"th = {threshold.value}")
            if split_pump:
                if frame_index % 2 == 0:
                    threshold_img += thresholded
                else:
                    threshold_img_pumped += thresholded
            else:
                threshold_img += thresholded
        if process_counting:
            clustered = no_ped > counting_threshold.value
            if split_pump:
                if frame_index % 2 == 0:
                    counting_img += clustered
                else:
                    counting_img_pumped += clustered
            else:
                counting_img += clustered
    processed_frames.value += 1
    print(f"Left processing frame {frame_index}")
    print(f"Processed frames {processed_frames.value}")
    lock.release()


if __name__ == "__main__":
    run((MoenchZmqServer,))
