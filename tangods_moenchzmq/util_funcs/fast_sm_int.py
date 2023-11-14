def write_int(sm, value):
    sm.buf[:] = int(value).to_bytes(length=8, byteorder="little", signed=False)


def get_int(sm):
    return int.from_bytes(sm.buf, byteorder="little", signed=False)
