from ctypes import *


class data_header(Structure):
    _fields_ = [
        ("timestamp", c_int)("filename", c_char_p),
        ("filepath", c_char_p),
        ("file_index", c_int),
        ("normalize", c_bool),
        ("threshold", c_float),
        ("counting_threshold", c_float),
        ("processing_pattern", c_char_p),
        ("processed_frames", c_int),
        ("received_frames", c_int),
        ("unpumped_frames", c_int),
        ("pumped_frames", c_int)("process_analog_img", c_bool),
        ("process_threshold_img", c_bool),
        ("process_counting_img", c_bool),
    ]
