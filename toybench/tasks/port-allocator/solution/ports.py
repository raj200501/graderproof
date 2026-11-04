def pick_port(used, low, high):
    for port in range(low, high + 1):
        if port not in used:
            return port
    return None
