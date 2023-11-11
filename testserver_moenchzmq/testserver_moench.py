from tangods_moenchzmq.util_funcs.parsers import *
from tangods_moenchzmq.util_funcs.buffers import *
from tangods_moenchzmq.proc_funcs.processing import processing_function

from .util.enums import ImageClass
from .util.frames import *
from .util.headers import *
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


class MoenchZmqTestServer(Device):
    ZMQ_TX_IP = device_property(
        dtype=str,
        doc="port of the slsReceiver instance, must match the config",
        default_value="127.0.0.1",
    )
    ZMQ_TX_PORT = device_property(
        dtype=str,
        doc="ip of slsReceiver instance, must match the config",
        default_value="50003",
    )

    gaussian_noise_sigma = attribute(
        label="noise sigma", access=AttrWriteType.READ_WRITE, dtype=int, unit="ADU"
    )

    background_offset = attribute(
        label="offset", access=AttrWriteType.READ_WRITE, dtype=int, unit="ADU"
    )

    image_class = attribute(
        label="img",
        access=AttrWriteType.READ_WRITE,
        dtype=ImageClass,
    )

    frames_amount = attribute(
        label="frames", access=AttrWriteType.READ_WRITE, dtype=int
    )

    framerate = attribute(
        label="framerate",
        access=AttrWriteType.READ_WRITE,
        dtype=float,
        unit="Hz",
        min_value=0.5,
    )

    single_photon_signal = attribute(
        label="single signal",
        access=AttrWriteType.READ_WRITE,
        dtype=float,
        unit="ADU",
        min_value=0,
    )

    def read_gaussian_noise_sigma(self):
        return self._gaussian_noise_sigma

    def write_gaussian_noise_sigma(self, value):
        self._gaussian_noise_sigma = value

    def read_background_offset(self):
        return self._background_offset

    def write_background_offset(self, value):
        self._background_offset = value

    def read_gaussian_noise_sigma(self):
        return self._gaussian_noise_sigma

    def write_gaussian_noise_sigma(self, value):
        self._gaussian_noise_sigma = value

    def read_image_class(self):
        return self._image_class

    def write_image_class(self, value):
        self._image_class = ImageClass(value)

    def read_frames_amount(self):
        return self._frames_amount

    def write_frames_amount(self, value):
        self._frames_amount = value

    def read_framerate(self):
        return self._framerate

    def write_framerate(self, value):
        self._framerate = value

    def read_single_photon_signal(self):
        return self._single_photon_signal

    def write_single_photon_signal(self, value):
        self._single_photon_signal = value

    def init_device(self):
        Device.init_device(self)
        self.set_state(DevState.INIT)
        self._gaussian_noise_sigma = 19
        self._background_offset = 5400
        self._image_class = ImageClass.PEDESTAL
        self._frames_amount = 100
        self._framerate = 100
        self._single_photon_signal = 100
        self.init_zmq()

        self.set_state(DevState.ON)

    def init_zmq(self):
        context = zmq.Context()
        self.socket = context.socket(zmq.PUB)
        self.socket.bind(f"tcp://{self.ZMQ_TX_IP}:{self.ZMQ_TX_PORT}")
        self.send_loop = asyncio.new_event_loop()

    @command
    def send_frames(self):
        self.send_loop.run_in_executor(None, self._send_frames)

    def _send_frames(self):
        self.set_state(DevState.RUNNING)
        for i in range(self._frames_amount):
            match self._image_class:
                case ImageClass.PEDESTAL:
                    frame = PedestalFrame(
                        self._background_offset, self._gaussian_noise_sigma
                    )
                case ImageClass.DIGITS:
                    frame = DigitFrame(
                        self._background_offset, self._gaussian_noise_sigma, i
                    )
                case ImageClass.SIMULATION:
                    frame = SimulationFrame(
                        self._background_offset,
                        self._gaussian_noise_sigma,
                        self._single_photon_signal,
                    )
            self.send_frame(frame, i)
            time.sleep(1 / self._framerate)
        self.set_state(DevState.ON)

    def send_frame(self, frame: Frame, frame_number: int):
        reordered = FrameUtils.inverse_reorder(frame.get_frame())
        if frame_number is not None:
            payload_header["frameIndex"] = frame_number
        self.socket.send_json(payload_header)
        self.socket.send(reordered.tobytes())
        self.socket.send_json(dummy_header)

    def delete_device(self):
        Device.delete_device(self)
