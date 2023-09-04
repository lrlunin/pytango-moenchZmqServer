from ctypes import *
import os


class DataHeader(Structure):
    _pack_ = 1
    _fields_ = [
        ("timestamp", c_int),
        ("filename", c_char_p),
        ("filepath", c_char_p),
        ("file_index", c_int),
        ("normalize", c_bool),
        ("threshold", c_float),
        ("counting_sigma", c_float),
        ("processing_pattern", c_char_p),
        ("processed_frames", c_int),
        ("received_frames", c_int),
        ("unpumped_frames", c_int),
        ("pumped_frames", c_int),
        ("process_analog_img", c_bool),
        ("process_threshold_img", c_bool),
        ("process_counting_img", c_bool),
    ]


HEADER_SIZE = sizeof(DataHeader)
FRAMETYPE_HEADER_SIZE = 2
# numpy 400x400 float array nbytes
CAPTURE_SIZE = 1280000
PROCESSING_MODES = 3
DATA_ENTRY_SIZE = FRAMETYPE_HEADER_SIZE + PROCESSING_MODES * CAPTURE_SIZE


def save_header(filename: str, header: DataHeader):
    fd = os.open(filename, os.O_WRONLY)
    os.pwritev(fd, bytearray(header), 0)
    os.fsync(fd)
    os.close(fd)


def save_frame(filename: str, frame_index: int, bytes_to_save: bytearray):
    frame_offset = HEADER_SIZE + frame_index * DATA_ENTRY_SIZE
    fd = os.open(filename, os.O_WRONLY)
    os.pwritev(fd, bytes_to_save, frame_offset)
    os.fsync(fd)
    os.close(fd)
