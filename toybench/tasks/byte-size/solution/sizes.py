_UNITS = [("TiB", 1024 ** 4), ("GiB", 1024 ** 3), ("MiB", 1024 ** 2), ("KiB", 1024)]


def format_size(n):
    if n < 1024:
        return "%d B" % n
    for name, size in _UNITS:
        if n >= size:
            tenths = (n * 20 + size) // (2 * size)
            return "%d.%d %s" % (tenths // 10, tenths % 10, name)
    raise AssertionError("unreachable")
