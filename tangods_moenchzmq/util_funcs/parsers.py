import re
import os
from os import path, makedirs, remove
from nexusformat.nexus import *


def get_mods(session_list, types_return_order=["ped", "p", "up"]):
    return_array = [[] for _ in range(len(types_return_order))]
    for i, key in enumerate(session_list):
        try:
            type_index = types_return_order.index(key)
            return_array[type_index].append(i)
        except ValueError:
            pass
    divisor = len(session_list)
    return divisor, return_array


def is_string_a_valid_array(value):
    # pattern for check if string a valid python array of strings (created by chatgpt :D)
    pattern = "^\[\s*(('[^']*')|(\"[^\"]*\"))(,\s*(('[^']*')|(\"[^\"]*\")))*\s*\]$"
    return re.match(pattern, value) and ("" not in eval(value))


def get_max_file_index(filepath, filename):
    # full_file_name_like = 202301031_run_5_.....tiff
    # get list of files in the directory
    file_list = os.listdir(filepath)

    # getting files which begin with the same filename
    captures_list = list(
        filter(lambda file_name: file_name.startswith(filename), file_list)
    )
    # if there is no files with this filename -> 0
    if len(captures_list) == 0:
        return 0
    # if there is any file with the same filename
    else:
        # finding index with regexp while index is a decimal number which stays after "filename_"
        # (\d*) - is an indented group 1
        r = re.compile(rf"^{filename}_(\d+).nxs$")
        # regex objects which match the upper statement
        reg = filter(lambda item: item is not None, map(r.search, captures_list))
        # getting max from the group 1 <=> index
        max_index = max(map(lambda match: int(match.group(1)), reg))
        return max_index


def create_temp_folder(savepath, temp_folder="temp"):
    if path.isdir(savepath):
        temp_path = path.join(savepath, temp_folder)
        if not path.isdir(temp_path):
            try:
                makedirs(temp_path)
            except OSError:
                pass
        return temp_path


def stack_partial_into_single(save_folder, temp_folder, filename, file_index):
    pattern = rf"^fileindex-{file_index}-frameindex-(\d+).nxs$"
    r = re.compile(pattern)
    files = os.listdir(temp_folder)
    main_entry = NXentry(name=f"fileindex{file_index}")
    for file in files:
        if re.match(pattern, file):
            frame_index = r.search(file).group(1)
            full_file_path = path.join(temp_folder, file)
            entry_name = f"frame{frame_index}"
            frame_entry = nxload(full_file_path)[entry_name]
            main_entry[entry_name] = frame_entry
            os.remove(full_file_path)
    full_save_path = path.join(save_folder, f"{filename}_{file_index}_all_frames.nxs")
    main_entry.save(full_save_path)
