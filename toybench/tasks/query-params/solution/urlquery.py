from urllib.parse import unquote_plus


def parse_query(qs):
    if qs.startswith("?"):
        qs = qs[1:]
    result = {}
    for pair in qs.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        result[unquote_plus(key)] = unquote_plus(value)
    return result
