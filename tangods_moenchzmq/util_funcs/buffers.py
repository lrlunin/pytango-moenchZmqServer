import numpy as np
from numba import njit


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


def push_to_ped_buffer(
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


@njit("void(f8[:,:], u1[:,:], f8[:,:], f8[:,:], f8[:,:])")
def fast_update_ped_buffer(
    frame, pedestal_mask, pedestal, pedestal_squared, pedestal_counter
):
    BUFFER_SIZE = 5000
    for y, x in np.argwhere(pedestal_mask):
        if pedestal_counter[y, x] < BUFFER_SIZE:
            pedestal_counter[y, x] += 1
            if pedestal_counter[y, x] == 1:
                pedestal[y, x] = frame[y, x]
                pedestal_squared[y, x] = frame[y, x] ** 2
            else:
                pedestal[y, x] += frame[y, x]
                pedestal_squared[y, x] += frame[y, x] ** 2
        else:
            if pedestal_counter[y, x] == 0:
                pedestal[y, x] = frame[y, x]
                pedestal_squared[y, x] = frame[y, x] ** 2
                pedestal_counter[y, x] += 1
            else:
                pedestal[y, x] = (
                    pedestal[y, x] + frame[y, x] - pedestal[y, x] / BUFFER_SIZE
                )
                pedestal_squared[y, x] = (
                    pedestal_squared[y, x]
                    + frame[y, x] ** 2
                    - pedestal_squared[y, x] / BUFFER_SIZE
                )


@njit("f8[:,:](f8[:,:], f8[:,:])")
def get_ped(pedestal_counter, pedestal):
    result = np.zeros((400, 400), dtype=float)
    for y in range(400):
        for x in range(400):
            if pedestal_counter[y, x] != 0:
                result[y, x] = pedestal[y, x] / pedestal_counter[y, x]
    return result


@njit("f8[:,:](f8[:,:], f8[:,:], f8[:,:])")
def get_ped_std(pedestal_counter, pedestal, pedestal_squared):
    result = np.zeros((400, 400), dtype=float)
    for y in range(400):
        for x in range(400):
            ped_counter = pedestal_counter[y, x]
            if ped_counter > 0:
                result[y, x] = (
                    pedestal_squared[y, x] / ped_counter
                    - (pedestal[y, x] / ped_counter) ** 2
                )
    return np.sqrt(result)
