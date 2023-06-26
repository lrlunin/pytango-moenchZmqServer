import re
import os


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
        r = re.compile(rf"^{filename}_(\d+)")
        # regex objects which match the upper statement
        reg = filter(lambda item: item is not None, map(r.search, captures_list))
        # getting max from the group 1 <=> index
        max_index = max(map(lambda match: int(match.group(1)), reg))
        return max_index
