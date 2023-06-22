def get_mods(session_list, types_return_order=["ped", "p", "up"]):
    return_array = [[] for _ in range(len(types_return_order))]
    for i, key in enumerate(session_list):
        try:
            type_index = types_return_order.index(key)
            return_array[type_index].append(i)
        except ValueError:
            pass
    return return_array


def is_string_a_valid_array(value):
    # pattern for check if string a valid python array of strings (created by chatgpt :D)
    pattern = "^\[\s*(('[^']*')|(\"[^\"]*\"))(,\s*(('[^']*')|(\"[^\"]*\")))*\s*\]$"
    return re.match(pattern, value) and ("" not in eval(value))
