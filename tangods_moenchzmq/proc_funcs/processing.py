from ..util_funcs.buffers import push_to_buffer
from .counting import getClustersSLS

import numpy as np
from enum import IntEnum
from nexusformat.nexus import *
from os import path


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
    pedestal_lock,
    shared_memories,
    processed_frames,
    threshold,
    counting_threshold,
    unpumped_frames,
    pumped_frames,
    pedestals_buffer_size,
    pedestal_indexes_shared_memory,
    pedestal_buffer_shared_memory,
    pedestal_frames_amount,
    event,
    update_period,
    save_separate_frames,
    fileindex,
    temp_filepath,
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
    pedestals_frame_buffer = np.ndarray(
        (pedestals_buffer_size, 400, 400),
        dtype=np.uint16,
        buffer=pedestal_buffer_shared_memory.buf,
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
    if frametype is FrameType.PEDESTAL:
        pedestal_lock.acquire()
        print("enter pedestal lock")
        push_to_buffer(
            indexes_buffer,
            pedestals_frame_buffer,
            pedestal_frames_amount.value,
            payload_copy,
            pedestal,
            pedestals_buffer_size,
        )
        pedestal_frames_amount.value += 1
        pedestal_lock.release()
        print("quit pedesal lock")
    else:
        pedestal_lock.acquire()
        pedestal_copy = np.copy(pedestal)
        pedestal_lock.release()
        analog = payload_copy - pedestal_copy
        if process_analog:
            pass
            print("Processing analog...")
        if process_threshold:
            print("Processing threshold...")
            thresholded = analog > threshold.value
            print(f"th = {threshold.value}")
        if process_counting:
            print("Processing counting...")
            clustered = getClustersSLS(analog, counting_threshold.value)
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
        event.set()
        # is actually not necessary, isn't it?
        # is it possible that update_from_event will update the image after finish in
        # concurrent race and will update an old image?
        event.wait()
    raw += payload
    print(f"Left processing frame {frame_index}")
    print(f"Processed frames {processed_frames.value}")
    lock.release()
    # the saving of the nexus file is pretty slow (approx 40ms)
    # in contrary saving of the python object with pickle took 14ms
    # the size of the serialized object is significantly bigger (7.7 MB vs 40.4 KB)
    if save_separate_frames:
        axes = ["raw", "pedestal"]
        images = [payload_copy, pedestal_copy]
        if frametype is not FrameType.PEDESTAL:
            if process_analog:
                axes.append("analog")
                images.append(analog)
            if process_threshold:
                axes.append("thresholded")
                images.append(thresholded)
            if process_counting:
                axes.append("clustered")
                images.append(clustered)
            images = np.array(images)
        metadata_dict = {"frame_index": frame_index, "frame_type": frametype.name}
        data = NXdata(signal=images, axes=axes)
        metadata = NXcollection(entries=metadata_dict)
        entry = NXentry(name=f"frame{frame_index}", data=data, metadata=metadata)
        filename = path.join(
            temp_filepath, f"fileindex-{fileindex}-frameindex-{frame_index}.nxs"
        )
        entry.save(filename)
