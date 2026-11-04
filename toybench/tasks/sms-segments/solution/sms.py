SINGLE_LIMIT = 160
PART_SIZE = 153


def split_sms(message):
    if len(message) <= SINGLE_LIMIT:
        return [message]
    return [message[i : i + PART_SIZE] for i in range(0, len(message), PART_SIZE)]
