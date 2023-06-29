import numpy as np


def push_to_buffer(
    indexes_array, pedestal_array, new_index, new_ped, pedestal, buf_size
):
    arg_min = np.argmin(indexes_array)
    old_data = np.copy(pedestal_array[arg_min])
    indexes_array[arg_min] = new_index
    pedestal_array[arg_min] = new_ped
    pedestal[:] = pedestal - old_data / buf_size + new_ped / buf_size
