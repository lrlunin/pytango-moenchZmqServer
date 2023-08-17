import numpy as np


def write_shared_array(shared_memory, value):
    array = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
    array[:] = value[:]


def read_shared_array(shared_memory, flip: bool):
    buf = np.ndarray((400, 400), dtype=float, buffer=shared_memory.buf)
    array = np.copy(buf)
    if flip:
        array = np.flipud(array)
    return array


def empty_shared_array(shared_value):
    array = np.ndarray((400, 400), dtype=float, buffer=shared_value.buf)
    array[:] = np.zeros_like(array)


def push_to_buffer(
    indexes_array, pedestal_array_sm, new_index, new_ped, pedestal, buf_size
):
    pedestal_array = np.ndarray(
        (buf_size, 400, 400),
        dtype=np.uint16,
        buffer=pedestal_array_sm.buf,
    )
    arg_min = np.argmin(indexes_array)
    old_data = np.copy(pedestal_array[arg_min])
    indexes_array[arg_min] = new_index
    pedestal_array[arg_min] = new_ped
    pedestal[:] = pedestal + (new_ped - old_data) / buf_size
