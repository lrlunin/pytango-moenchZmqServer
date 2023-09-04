from tangods_moenchzmq.util_funcs.buffers import (
    push_to_ped_buffer,
    fast_update_ped_buffer,
    get_ped_std,
    get_ped,
)
from tangods_moenchzmq.proc_funcs.counting import getClustersSLS, classifyPixel

import numpy as np
from enum import IntEnum
from nexusformat.nexus import *
from os import path
from functools import reduce
from dataformat_moenchzmq.datatype import save_frame, FRAMETYPE_HEADER_SIZE


class FrameType(IntEnum):
    PEDESTAL = 0
    PUMPED = 1
    UNPUMPED = 2


def processing_function(
    processing_indexes_divisor,
    processing_indexes_array,
    use_modes,
    header,
    payload,
    lock,
    rmutex,
    wmutex,
    readTry,
    resource,
    readcount,
    writecount,
    shared_memories,
    processed_frames,
    threshold,
    counting_sigma,
    unpumped_frames,
    pumped_frames,
    pedestals_buffer_size,
    pedestal_indexes_shared_memory,
    pedestal_buffer_shared_memory,
    pedestal_frames_amount,
    push_event,
    ready_event,
    update_period,
    save_separate_frames,
    raw_file_fullpath,
    shared_memory_pedestal_counter,
    shared_memory_pedestal_squared,
):
    # use_modes = [self.read_process_pedestal_img(),  self.read_process_analog_img(), self.read_process_threshold_img(), self.read_process_counting_img()]
    # [
    #     self.shared_memory_pedestal,
    #     self.shared_memory_analog_img,
    #     self.shared_memory_analog_img_pumped,
    #     self.shared_memory_threshold_img,
    #     self.shared_memory_threshold_img_pumped,
    #     self.shared_memory_counting_img,
    #     self.shared_memory_counting_img_pumped,
    #     self.shared_memory_raw_img,
    # ]
    def wlock():
        wmutex.acquire()
        writecount.value += 1
        if writecount.value == 1:
            readTry.acquire()
        wmutex.release()
        resource.acquire()

    def wrelease():
        resource.release()
        wmutex.acquire()
        writecount.value -= 1
        if writecount.value == 0:
            readTry.release()
        wmutex.release()

    def rlock():
        readTry.acquire()
        rmutex.acquire()
        readcount.value += 1
        if readcount.value == 1:
            resource.acquire()
        rmutex.release()
        readTry.release()

    def rrelease():
        rmutex.acquire()
        readcount.value -= 1
        if readcount.value == 0:
            resource.release()
        rmutex.release()

    process_pedestal, process_analog, process_threshold, process_counting = use_modes
    pedestal_indexes, pumped_indexes, unpumped_indexes = processing_indexes_array
    divisor = processing_indexes_divisor
    # get frame index from json header to determine the frame ordinal number
    frame_index = header.get("frameIndex")
    """
    creating a numpy array with copy of the uncoming frame
    casting up to float due to the further pedestal subtraction (averaged pedestal will have fractional part)
    """
    payload_copy = payload.astype(float, copy=True)
    # creating numpy arrays from shared memories; could not be automatically created with locals()["..."]
    pedestal = np.ndarray((400, 400), dtype=float, buffer=shared_memories[0].buf)
    analog_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[1].buf)
    analog_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[2].buf
    )
    threshold_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[3].buf)
    threshold_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[4].buf
    )
    counting_img = np.ndarray((400, 400), dtype=float, buffer=shared_memories[5].buf)
    counting_img_pumped = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memories[6].buf
    )
    raw = np.ndarray((400, 400), dtype=float, buffer=shared_memories[7].buf)
    indexes_buffer = np.ndarray(
        pedestals_buffer_size, dtype=np.int32, buffer=pedestal_indexes_shared_memory.buf
    )
    pedestal_counter = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memory_pedestal_counter.buf
    )
    pedestal_squared = np.ndarray(
        (400, 400), dtype=float, buffer=shared_memory_pedestal_squared.buf
    )
    # calculations oustide of lock
    # variables assignments inside of lock

    print(f"Enter processing frame {frame_index}")

    # we need to classify the frame (is it new pedestal/pumped/unpumped) before the processing
    # later configurable with str array like sequence: [unpumped, ped, ped, ped, pumped, ped, ped, ped,]
    frametype = None
    mod = None
    if divisor != 0:
        mod = frame_index % divisor
    if mod in pedestal_indexes:
        frametype = FrameType.PEDESTAL
    elif mod in pumped_indexes:
        frametype = FrameType.PUMPED
    elif mod in unpumped_indexes:
        frametype = FrameType.UNPUMPED
    else:
        frametype = FrameType.UNPUMPED
    if process_pedestal:
        frametype = FrameType.PEDESTAL
    rlock()
    print("enter pedestal rlock")
    pedestal_counter_copy = np.copy(pedestal_counter)
    pedestal_squared_copy = np.copy(pedestal_squared)
    pedestal_copy = np.copy(pedestal)
    print("quit pedestal rlock")
    rrelease()

    divided_ped = get_ped(pedestal_counter_copy, pedestal_copy)
    pedestal_std = get_ped_std(
        pedestal_counter_copy, pedestal_copy, pedestal_squared_copy
    )
    analog = payload_copy - divided_ped

    pixel_classes = classifyPixel(analog, pedestal_std, counting_sigma)
    pedestal_pixels = pixel_classes == 0
    photon_pixels = pixel_classes == 1
    photon_max_pixels = pixel_classes == 2
    if frametype is FrameType.PEDESTAL:
        pedestal_pixels = np.ones((400, 400), dtype=np.int8)
    wlock()
    fast_update_ped_buffer(
        payload_copy,
        pedestal_pixels.astype(np.uint8),
        pedestal,
        pedestal_squared,
        pedestal_counter,
    )
    wrelease()
    if frametype is not FrameType.PEDESTAL:
        if process_analog:
            print("Processing analog...")
        if process_threshold:
            print("Processing threshold...")
            thresholded = analog > threshold
            print(f"th = {threshold}")
        if process_counting:
            print("Processing counting...")
            clustered = photon_max_pixels.astype(np.int16)

    if save_separate_frames:
        databytes = int(frametype).to_bytes(FRAMETYPE_HEADER_SIZE, "big")
        if frametype == FrameType.PEDESTAL:
            databytes += payload_copy.tobytes
        else:
            # if too slow - save with different offsets instead of joining
            array_to_bytes = map(lambda x: x.tobytes(), [analog, threshold, clustered])
            databytes += reduce((lambda x, y: x + y), array_to_bytes)
        save_frame(raw_file_fullpath, frame_index, databytes)

    lock.acquire()
    match frametype:
        case FrameType.UNPUMPED:
            if process_analog:
                analog_img += analog
            if process_threshold:
                threshold_img += thresholded
            if process_counting:
                counting_img += clustered
            unpumped_frames.value += 1
        case FrameType.PUMPED:
            if process_analog:
                analog_img_pumped += analog
            if process_threshold:
                threshold_img_pumped += thresholded
            if process_counting:
                counting_img_pumped += clustered
            pumped_frames.value += 1
    processed_frames.value += 1
    if update_period != 0 and processed_frames.value % update_period == 0:
        ready_event.clear()
        push_event.set()
        ready_event.wait()
    raw += payload
    print(f"Left processing frame {frame_index}")
    print(f"Processed frames {processed_frames.value}")
    lock.release()
