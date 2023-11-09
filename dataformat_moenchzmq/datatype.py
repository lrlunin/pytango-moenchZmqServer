from ctypes import *
import os
from multiprocessing import shared_memory as sm


class DataHeaderv1(Structure):
    _pack_ = 1
    _fields_ = [
        ("header_version", c_int),
        ("header_size", c_int),
        ("timestamp", c_int),
        ("filename", c_byte * 4096),  # path in linux can be 4096 chars long
        ("filepath", c_byte * 4096),  # path in linux can be 4096 chars long
        ("file_index", c_int),
        ("normalize", c_bool),
        ("threshold", c_float),
        ("counting_sigma", c_float),
        ("processing_pattern", c_byte * 4096),  # path in linux can be 4096 chars long
        ("processed_frames", c_int),
        ("received_frames", c_int),
        ("unpumped_frames", c_int),
        ("pumped_frames", c_int),
        ("process_analog_img", c_bool),
        ("process_threshold_img", c_bool),
        ("process_counting_img", c_bool),
    ]

    def __init__(self, *args, header_version=1, **kw):
        super().__init__(
            *args, header_version=header_version, header_size=sizeof(self), **kw
        )


class DataHeaderv2(DataHeaderv1):
    _fields_ = [("extra_param2", c_byte * 255)]

    def __init__(self, *args, header_version=2, **kw):
        super().__init__(*args, header_version=header_version, **kw)


class DataHeaderv3(DataHeaderv2):
    _fields_ = [("extra_param3", c_byte * 255)]

    def __init__(self, *args, header_version=3, **kw):
        super().__init__(*args, header_version=header_version, **kw)


class DataStructurev1(Structure):
    _pack_ = 1
    _fields_ = [
        ("data_version", c_int),
        ("data_size", c_int),
        ("frame_index", c_int),
        ("frame_type", c_int),  # 0 - ped, 1 - pumped, 2 - unpumped
        ("pedestal", c_byte * 1280000),
        ("analog", c_byte * 1280000),
        ("threshold", c_byte * 1280000),
        ("clustered", c_byte * 1280000),
    ]

    def __init__(self, *args, data_version=1, **kw):
        super().__init__(*args, data_version=data_version, data_size=sizeof(self), **kw)


class DataStructurev2(DataStructurev1):
    _fields_ = [("extra_param2", c_byte * 255)]

    def __init__(self, *args, data_version=2, **kw):
        super().__init__(*args, data_version=data_version, **kw)


def set_header(shared_memory: sm.SharedMemory, header: DataHeaderv1):
    shared_memory.buf[0 : header.header_size] = bytearray(header)


def set_frame(
    shared_memory: sm.SharedMemory, header_size: int, data_structure: DataStructurev1
):
    data_size = data_structure.data_size
    offset = header_size + data_size * data_structure.frame_index
    shared_memory.buf[offset, offset + data_size] = bytearray(data_structure)


def dump_memory(filename, shared_memory: sm.SharedMemory):
    with open(filename, "wb") as bfile:
        bfile.write(shared_memory.buf)
