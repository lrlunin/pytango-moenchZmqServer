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
        self.parse_versions()

    def parse_versions(self):
        self._header_type = self.get_header_type()
        self._header_size = self.get_header_size()

        self._data_type = self.get_data_type()
        self._data_size = self._data_type().data_size

    def get_header_type(self) -> type:
        header_version = int.from_bytes(
            os.pread(self._fd, ct.sizeof(ct.c_uint64), 0),
            byteorder="little",
            signed=False,
        )
        header_type = dt.header_version.get(header_version)
        if header_type is None:
            raise Exception(f"Not supported header version {header_version}!")
        else:
            print(f"Parsed header {header_type.__name__}")
            return header_type

    def get_header_size(self) -> int:
        header_size = int.from_bytes(
            os.pread(self._fd, ct.sizeof(ct.c_uint64), ct.sizeof(ct.c_uint64)),
            byteorder="little",
            signed=False,
        )
        return header_size

    def get_data_type(self) -> type:
        data_version = int.from_bytes(
            os.pread(self._fd, ct.sizeof(ct.c_uint64), 2 * ct.sizeof(ct.c_uint64)),
            byteorder="little",
            signed=False,
        )
        data_type = dt.data_version.get(data_version)
        if data_type is None:
            raise Exception(f"Not supported data version {data_version}!")
        else:
            print(f"Parsed header {data_type.__name__}")
            return data_type

    def __del__(self) -> None:
        os.close(self._fd)

    def get_header(self) -> dt.DataHeaderv1:
        header_bytes = os.pread(self._fd, self._header_size, 0)
        return self._header_type(header_bytes)

    def get_data(self, frame_index: int) -> dt.DataStructurev1:
        offset = self._header_size + frame_index * self._data_size
        data_bytes = os.pread(self._fd, self._data_size, offset)
        return self._data_type(data_bytes)

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
