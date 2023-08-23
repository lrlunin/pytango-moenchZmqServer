import os
import ctypes as ct
import dataformat_moenchzmq.datatype as dt
from tangods_moenchzmq.proc_funcs.processing import FrameType
from nexusformat.nexus import *
import numpy as np


class Converter:
    def __init__(self, input_file_path: str) -> None:
        self._input_file_path = input_file_path
        self._fd = os.open(self._input_file_path, os.O_RDONLY)
        self.parse_header()

    def __del__(self) -> None:
        os.close(self._fd)

    def parse_header(self) -> None:
        bytes = os.pread(self._fd, dt.HEADER_SIZE, 0)
        self._dh = dt.DataHeader(bytes)

    def get_header_as_dict(self) -> dict:
        format_str = lambda x, y: x if y != ct.c_char_p else x.encode("utf-8")
        return dict(
            (field, format_str(getattr(self._dh, field), dtype))
            for field, dtype in self._dh._fields_
        )

    def convert_to_nexus(self, nexus_filename) -> None:
        processed_frames = self._dh.processed_frames
        header = self.get_header_as_dict()
        for frame_nr in processed_frames:
            offset = dt.HEADER_SIZE + frame_nr * dt.DATA_ENTRY_SIZE
            data_bytes = os.pread(self._fd, dt.DATA_ENTRY_SIZE, offset)
            frametype = FrameType(
                int.from_bytes(data_bytes[: dt.FRAMETYPE_HEADER_SIZE], "big")
            )
            captures = np.zeros((dt.PROCESSING_MODES, 400, 400), dtype=float)
            for i in range(dt.PROCESSING_MODES):
                read_offset = dt.FRAMETYPE_HEADER_SIZE + i * dt.CAPTURE_SIZE
                captures[i] = np.frombuffer(
                    data_bytes,
                    dtype=float,
                    offset=read_offset,
                    count=dt.CAPTURE_SIZE,
                ).reshape((400, 400))
            # TBD
