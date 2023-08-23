from tangods_moenchzmq.util_funcs.parsers import *
from tangods_moenchzmq.util_funcs.buffers import *
from tangods_moenchzmq.proc_funcs.processing import processing_function

import asyncio
import json
import multiprocessing as mp
from nexusformat.nexus import *
from importlib.resources import files

from os import path, makedirs
import time, shutil, threading
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.managers import SharedMemoryManager
import sys
import numpy as np
import zmq
import zmq.asyncio
from tango import AttrDataFormat, AttrWriteType, DevState, DispLevel, GreenMode, Except
from tango.server import (
    Device,
    attribute,
    command,
    device_property,
    run,
)


class MoenchZmqServer(Device):
    """Custom implementation of zmq processing server for X-ray detector MOENCH made in PSI which is integrated with a Tango device server."""

    processing_pattern_string = '["up"]'
    processing_indexes_array = [0]
    processing_indexes_divisor = 1
    _save_separate_frames = False
    _temp_path = ""

    _manager = None
    _context = None
    _socket = None
    _process_pool = None
    _IMG_ATTR = [
        "pedestal",
        "analog_img",
        "analog_img_pumped",
        "threshold_img",
        "threshold_img_pumped",
        "counting_img",
        "counting_img_pumped",
        "raw_img",
    ]
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
    # shared scalar values
    shared_threshold = None
    shared_counting_threshold = None
    shared_processed_frames = None
    shared_received_frames = None
    shared_unpumped_frames = None
    shared_pumped_frames = None
    shared_receive_frames = None
    shared_pedestal_frames = None
    _split_pump = False
    _process_pedestal_img = False
    _process_analog_img = True
    _process_threshold_img = True
    _process_counting_img = False

    # reorder table for frame
    reorder_table = None

    _filename = ""
    _filepath = ""
    _file_index = 0
    _normalize = True
    _update_period = 0
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
    PEDESTAL_FRAME_BUFFER_SIZE = device_property(
        dtype=int,
        doc="length of buffer for pedestal moving average",
        default_value=5000,
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
    space_available = attribute(
        label="space left at selected filepath",
        unit="GB",
        dtype=float,
        access=AttrWriteType.READ,
        doc="space left on the device used for save",
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
    normalize = attribute(
        label="normalize",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc="if true - normalize the images like 1 frame (divide through frames number)",
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
    processing_pattern = attribute(
        label="proc pattern",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
        doc='desc of sequence of frames. possible vales "ped", "p" and "up" for pedestal, pumped and unpumped images respectively',
    )
    update_period = attribute(
        label="live period",
        unit="frames",
        dtype=int,
        min_value=0,
        access=AttrWriteType.READ_WRITE,
        doc="push event each N frames. if 0 - no live updates",
    )
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
    unpumped_frames = attribute(
        display_level=DispLevel.EXPERT,
        label="unpumped frames",
        dtype=int,
        access=AttrWriteType.READ,
        doc="received unpumped frames",
    )
    pumped_frames = attribute(
        display_level=DispLevel.EXPERT,
        label="pumped frames",
        dtype=int,
        access=AttrWriteType.READ,
        doc="received pumped frames",
    )

    receive_frames = attribute(
        display_level=DispLevel.EXPERT,
        label="receive frames?",
        dtype=bool,
        access=AttrWriteType.READ,
        doc="if true - server receives frames, otherwise - ignores",
    )
    pedestal_frames = attribute(
        display_level=DispLevel.EXPERT,
        label="proc pedestal amount",
        dtype=int,
        access=AttrWriteType.READ,
        doc="how many pedestal frames were captured since the server started",
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

    save_separate_frames = attribute(
        label="save frames ind-ly",
        dtype=bool,
        access=AttrWriteType.READ_WRITE,
        memorized=True,
        hw_memorized=True,
    )

    temp_filepath = attribute(
        display_level=DispLevel.EXPERT,
        label="temp path for seperate frames",
        dtype=str,
        access=AttrWriteType.READ_WRITE,
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

    def write_space_available(self, value):
        pass

    def read_space_available(self):
        filepath = self.read_filepath()
        result = 0
        if path.isdir(filepath):
            total, used, free = shutil.disk_usage(filepath)
            # conversion to GiB
            result = free / 2**30
        return result

    def write_file_index(self, value):
        self._file_index = value

    def read_file_index(self):
        return self._file_index

    def write_normalize(self, value):
        self._normalize = bool(value)

    def read_normalize(self):
        return self._normalize

    def write_previous_file_index(self, value):
        pass

    def read_previous_file_index(self):
        return self.read_file_index() - 1

    def write_pedestal(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[0], value=value)

    def read_pedestal(self):
        return read_shared_array(
            shared_memory=self.shared_memory_buffers[0], flip=self.FLIP_IMAGE
        )

    def write_analog_img(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[1], value=value)

    def read_analog_img(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[1], flip=flip)

    def write_analog_img_pumped(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[2], value=value)

    def read_analog_img_pumped(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[2], flip=flip)

    def write_threshold_img(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[3], value=value)

    def read_threshold_img(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[3], flip=flip)

    def write_threshold_img_pumped(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[4], value=value)

    def read_threshold_img_pumped(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[4], flip=flip)

    def write_counting_img(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[5], value=value)

    def read_counting_img(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[5], flip=flip)

    def write_counting_img_pumped(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[6], value=value)

    def read_counting_img_pumped(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[6], flip=flip)

    def write_raw_img(self, value):
        write_shared_array(shared_memory=self.shared_memory_buffers[7], value=value)

    def read_raw_img(self, flip=None):
        if flip is None:
            flip = self.FLIP_IMAGE
        return read_shared_array(shared_memory=self.shared_memory_buffers[7], flip=flip)

    def write_threshold(self, value):
        # with self.shared_threshold.get_lock():
        self.shared_threshold.value = value

    def read_threshold(self):
        return self.shared_threshold.value

    def write_counting_threshold(self, value):
        self.shared_counting_threshold.value = value

    def read_counting_threshold(self):
        return self.shared_counting_threshold.value

    def write_processing_pattern(self, value):
        self.processing_pattern_string = value
        if is_string_a_valid_array(value):
            parsed_array = eval(value)
            self.processing_indexes_divisor, self.processing_indexes_array = get_mods(
                parsed_array
            )

    def read_processing_pattern(self):
        return self.processing_pattern_string

    def write_update_period(self, value):
        self._update_period = value

    def read_update_period(self):
        return self._update_period

    def write_processed_frames(self, value):
        self.shared_processed_frames.value = value

    def read_processed_frames(self):
        return self.shared_processed_frames.value

    def write_received_frames(self, value):
        self.shared_received_frames.value = value

    def read_received_frames(self):
        return self.shared_received_frames.value

    def write_unpumped_frames(self, value):
        self.shared_unpumped_frames.value = value

    def read_unpumped_frames(self):
        return self.shared_unpumped_frames.value

    def write_pumped_frames(self, value):
        self.shared_pumped_frames.value = value

    def read_pumped_frames(self):
        return self.shared_pumped_frames.value

    def write_receive_frames(self, value):
        self.shared_receive_frames.value = bool(value)

    def read_receive_frames(self):
        return bool(self.shared_receive_frames.value)

    def write_pedestal_frames(self, value):
        self.shared_pedestal_frames.value = value

    def read_pedestal_frames(self):
        return self.shared_pedestal_frames.value

    def write_split_pump(self, value):
        self._split_pump = bool(value)
        if self._split_pump:
            self.write_processing_pattern('["up", "p"]')
        else:
            self.write_processing_pattern('["up"]')

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

    def write_save_separate_frames(self, value):
        self._save_separate_frames = value

    def read_save_separate_frames(self):
        return self._save_separate_frames

    def write_temp_filepath(self, value):
        self._temp_filepath = value

    def read_temp_filepath(self):
        return self._temp_filepath

    def update_from_event(self):
        while True:
            self._push_event.wait()
            self.update_images_events()
            self._push_event.clear()
            self._ready_event.set()

    async def main(self):
        while True:
            header, payload = await self.get_msg_pair()
            if payload is not None and self.read_receive_frames():
                # received frames increment only in case the frame is not corrupted (reshaping is on)
                self.shared_received_frames.value += 1
                # see in docs
                # should be moved to each process to prevent performance bottleneck
                self._process_pool.submit(
                    processing_function,
                    self.processing_indexes_divisor,
                    self.processing_indexes_array,
                    [
                        self.read_process_pedestal_img(),
                        self.read_process_analog_img(),
                        self.read_process_threshold_img(),
                        self.read_process_counting_img(),
                    ],
                    header,
                    payload,
                    self._lock,
                    self.rmutex,
                    self.wmutex,
                    self.readTry,
                    self.resource,
                    self.readcount,
                    self.writecount,
                    self.shared_memory_buffers,
                    self.shared_processed_frames,
                    self.shared_threshold,
                    self.shared_counting_threshold,
                    self.shared_unpumped_frames,
                    self.shared_pumped_frames,
                    self.PEDESTAL_FRAME_BUFFER_SIZE,
                    self.shared_memory_pedestals_indexes,
                    self.shared_memory_pedestals_buffer,
                    self.shared_pedestal_frames,
                    self._push_event,
                    self._ready_event,
                    self._update_period,
                    self._save_separate_frames,
                    self._file_index,
                    self._temp_filepath,
                )

    async def get_msg_pair(self):
        isNextPacketData = True
        header = None
        payload = None
        packet1 = await self._socket.recv()
        try:
            # print("parsing header...")
            header = json.loads(packet1)
            isNextPacketData = header.get("data") == 1
            # print(f"isNextPacketdata {isNextPacketData}")
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

    @command
    def start_receiver(self):
        # clear previous values
        self.write_processed_frames(0)
        self.write_received_frames(0)
        self.write_unpumped_frames(0)
        self.write_pumped_frames(0)

        # 0 - is the pedestal, does not need to be reset each time...
        for buffer in self.shared_memory_buffers[1:]:
            empty_shared_array(buffer)
        self.write_receive_frames(True)
        # the self.update_images_events() is not working here
        # for unknown reason
        # for attr in self._IMG_ATTR:
        #     # call corresponding read_... functions with eval(...) instead of write it for each function call
        #     self.push_change_event(attr, eval(f"self.read_{attr}()"), 400, 400)
        self.set_state(DevState.RUNNING)

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
        # normalization for all other images
        unpumped_frames = self.read_unpumped_frames()
        pumped_frames = self.read_pumped_frames()
        if self.read_normalize():
            if unpumped_frames != 0:
                self.write_analog_img(
                    self.read_analog_img(flip=False) / unpumped_frames
                )
                self.write_threshold_img(
                    self.read_threshold_img(flip=False) / unpumped_frames
                )
                self.write_counting_img(
                    self.read_counting_img(flip=False) / unpumped_frames
                )
            if pumped_frames != 0:
                self.write_analog_img_pumped(
                    self.read_analog_img_pumped(flip=False) / pumped_frames
                )
                self.write_threshold_img_pumped(
                    self.read_threshold_img_pumped(flip=False) / pumped_frames
                )
                self.write_counting_img_pumped(
                    self.read_counting_img_pumped(flip=False) / pumped_frames
                )
        # HERE ALL POST HOOKS
        self.update_images_events()
        self.save_nexus_file()
        file_index = self.read_file_index()
        if self.read_save_separate_frames():
            filepath = self.read_filepath()
            temp_folder = self.read_temp_filepath()
            filename = self.read_filename()
            threading.Thread(
                daemon=True,
                target=stack_partial_into_single,
                args=(
                    filepath,
                    temp_folder,
                    filename,
                    file_index,
                ),
            ).start()
        self.write_file_index(file_index + 1)
        self.set_state(DevState.ON)

    @command
    async def stop_receiver(self):
        received_frames = self.shared_received_frames.value
        print(f"received {received_frames} frames")
        asyncio.set_event_loop(self.functions_loop)
        self.functions_loop.run_in_executor(
            None, self.block_stop_receiver, received_frames
        )

    @command
    def abort_receiver(self):
        self._abort_await = True

    @command
    def reset_pedestal(self):
        self._reset_pedestal()

    def init_device(self):
        """Initial tangoDS setup"""
        Device.init_device(self)
        self.set_state(DevState.INIT)
        self.get_device_properties(self.get_device_class())
        self.reorder_table = np.load(
            files("tangods_moenchzmq.reorder_tables").joinpath("moench03.npy")
        )
        # sync manager for synchronization between threads
        self._manager = mp.Manager()
        # using simple mutex (lock) to synchronize
        self._lock = self._manager.Lock()
        self._push_event = self._manager.Event()
        self._push_event.clear()
        self._ready_event = self._manager.Event()
        self._ready_event.clear()
        # extra pedestal lock for pedestal evaluation
        self._pedestal_lock = self._manager.Lock()

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
        max_file_index = get_max_file_index(self.read_filepath(), self.read_filename())
        self.write_file_index(max_file_index + 1)

        # using shared thread-safe Value instance from multiprocessing
        self.shared_threshold = self._manager.Value("f", 0)
        self.shared_counting_threshold = self._manager.Value("f", 0)
        self.shared_receive_frames = self._manager.Value("b", 0)
        self.shared_pedestal_frames = self._manager.Value("I", 0)
        self.shared_processed_frames = self._manager.Value("I", 0)
        self.shared_received_frames = self._manager.Value("I", 0)
        self.shared_unpumped_frames = self._manager.Value("I", 0)
        self.shared_pumped_frames = self._manager.Value("I", 0)
        self.shared_amount_frames = self._manager.Value("I", 0)
        self.shared_split_pump = self._manager.Value("b", 0)

        # for multipocessing rwlock
        self.rmutex, self.wmutex, self.readTry, self.resource = [
            self._manager.Semaphore() for i in range(0, 4)
        ]
        self.readcount, self.writecount = [
            self._manager.Value("i", 0) for i in range(0, 2)
        ]

        # calculating how many bytes need to be allocated and shared for a 400x400 float numpy array
        img_bytes = np.zeros((400, 400), dtype=float).nbytes
        # allocating 1x400x400 arrays for images
        # 7 arrays: pedestal, analog_img, analog_img_pumped, threshold_img, threshold_img_pumped, counting_img, counting_img_pumped
        self.shared_memory_buffers = []
        for i in range(0, 8):
            self.shared_memory_buffers.append(
                self._shared_memory_manager.SharedMemory(size=img_bytes)
            )
        pedestals_buffer_bytes = np.zeros(
            [self.PEDESTAL_FRAME_BUFFER_SIZE, 400, 400], dtype=np.uint16
        ).nbytes
        indexes_buffer_bytes = np.zeros(
            self.PEDESTAL_FRAME_BUFFER_SIZE, dtype=np.int32
        ).nbytes
        self.shared_memory_pedestals_buffer = self._shared_memory_manager.SharedMemory(
            size=pedestals_buffer_bytes
        )
        self.shared_memory_pedestals_indexes = self._shared_memory_manager.SharedMemory(
            size=indexes_buffer_bytes
        )
        self._reset_pedestal()
        # creating thread pool executor to which the frame processing will be assigned
        self._process_pool = ProcessPoolExecutor(processing_cores_amount)

        # creating and initialing socket to read from
        self._init_zmq_socket(zmq_ip, zmq_port)
        self.main_loop = asyncio.new_event_loop()
        self.functions_loop = asyncio.new_event_loop()
        self.event_loop = asyncio.new_event_loop()
        self.save_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.main_loop)
        asyncio.create_task(self.main())
        self.event_loop.run_in_executor(None, self.update_from_event)

        # assigning the previews for the images (just for fun)
        modes = ["analog", "threshold", "counting"]
        pump_states = ["unpumped", "pumped"]
        index = 1
        for mode in modes:
            for pump_state in pump_states:
                write_shared_array(
                    self.shared_memory_buffers[index],
                    np.load(
                        files("tangods_moenchzmq.default_images").joinpath(
                            f"{mode}_{pump_state}.npy"
                        )
                    ),
                )
                index += 1
        self.write_temp_filepath(create_temp_folder(self.read_filepath()))
        # initialization of tango events for pictures buffers
        for attr in self._IMG_ATTR:
            self.set_change_event(attr, True, False)
        self.set_state(DevState.ON)

    # updating of tango events for pictures buffers
    @command
    def update_images_events(self):
        for attr in self._IMG_ATTR:
            # call corresponding read_... functions with eval(...) instead of write it for each function call
            self.push_change_event(attr, eval(f"self.read_{attr}()"), 400, 400)

    def save_nexus_file(self):
        filepath = self.read_filepath()
        filename = self.read_filename()
        index = self.read_file_index()
        datetime_now = datetime.now()
        # need to be refactored soon
        field_names = self._IMG_ATTR
        images = np.zeros((len(field_names), 400, 400))
        for i, attr in enumerate(field_names):
            images[i] = eval(f"self.read_{attr}()")
        # file will be saved like
        savepath = path.join(filepath, f"{filename}_{index}")

        data = NXdata(signal=images, axes=field_names)
        # needs to include exposure time etc
        metadata_attributes = [
            "normalize",
            "threshold",
            "counting_threshold",
            "processing_pattern",
            "processed_frames",
            "unpumped_frames",
            "pumped_frames",
            "pedestal_frames",
        ]
        metadata_dict = {"end_time": datetime_now.isoformat()}
        for attr in metadata_attributes:
            metadata_dict[attr] = eval(f"self.read_{attr}()")

        metadata = NXcollection(entries=metadata_dict)
        metadata["threshold"].units = "ADU"
        metadata["counting_threshold"].units = "ADU"
        entry = NXentry(name=f"entry{index}", data=data, metadata=metadata)
        if path.isfile(f"{savepath}.nxs"):
            time_str = datetime_now.strftime("%H:%M:%S")
            savepath += f"_{time_str}"
        entry.save(f"{savepath}.nxs")

    def _init_zmq_socket(self, zmq_ip: str, zmq_port: str):
        endpoint = f"tcp://{zmq_ip}:{zmq_port}"
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        print(f"Connecting to: {endpoint}")
        self._socket.connect(endpoint)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")
        hwm = self._socket.get_hwm()
        print(f"HWM of the socket = {hwm}")

    def _reset_pedestal(self):
        indexes_array = np.ndarray(
            self.PEDESTAL_FRAME_BUFFER_SIZE,
            dtype=np.int32,
            buffer=self.shared_memory_pedestals_indexes.buf,
        )
        frames_array = np.ndarray(
            (self.PEDESTAL_FRAME_BUFFER_SIZE, 400, 400),
            dtype=np.uint16,
            buffer=self.shared_memory_pedestals_buffer.buf,
        )
        indexes_array[:] = -np.arange(self.PEDESTAL_FRAME_BUFFER_SIZE) - 1
        frames_array[:] = 0
        empty = np.zeros((400, 400), dtype=float)
        self.write_pedestal(empty)

    def delete_device(self):
        self._process_pool.shutdown(wait=False, cancel_futures=True)
        self._manager.shutdown()
        self._shared_memory_manager.shutdown()


if __name__ == "__main__":
    args = ["MoenchZmqServer"] + sys.argv[1:]
    run((MoenchZmqServer,), args=args)
