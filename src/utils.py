def millisecond_to_minute_second(milliseconds: int):
    """
    Convert a duration in milliseconds to a mm:ss formatted string.
    :param milliseconds: Duration in milliseconds
    :return: Duration formatted as mm:ss
    """
    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:2}:{seconds:02}"

def split_id(raw_id: str):
    year, id_num = raw_id.split("-")
    return int(year), int(id_num)