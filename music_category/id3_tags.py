from mutagen.id3 import GRP1, ID3, ID3NoHeaderError, TIT1, TXXX

from . import config


COLOR_KEYS = ("TXXX:Color", "TXXX:COLOR", "TXXX:color", "TXXX:Colour", "TXXX:COLOUR", "TXXX:colour")
GROUPING_KEYS = ("TIT1", "GRP1", "TXXX:GROUPING", "TXXX:Grouping", "TXXX:grouping")


def tag_text(tags, key):
    values = tag_text_values(tags, key)
    return "; ".join(values)


def tag_text_values(tags, key):
    frame = tags.get(key)
    if frame is None or not getattr(frame, "text", None):
        return []
    return [str(item).strip() for item in frame.text if str(item).strip()]


def read_color(tags):
    for key in COLOR_KEYS:
        values = tag_text_values(tags, key)
        if values:
            return values[-1]
    return ""


def read_id3(file_path):
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return {
            "artist": "",
            "title": "",
            "album": "",
            "genre": "",
            "id3_grouping": "",
            "id3_grouping_normalized": "",
            "id3_color": "",
            "id3_color_normalized": "",
        }

    grouping = ""
    for key in ("TIT1", "TXXX:GROUPING", "TXXX:Grouping", "TXXX:grouping"):
        values = tag_text_values(tags, key)
        if values:
            grouping = values[-1]
            break
    color = read_color(tags)
    return {
        "artist": tag_text(tags, "TPE1"),
        "title": tag_text(tags, "TIT2"),
        "album": tag_text(tags, "TALB"),
        "genre": tag_text(tags, "TCON"),
        "id3_grouping": grouping,
        "id3_grouping_normalized": config.normalize_grouping(grouping),
        "id3_color": color,
        "id3_color_normalized": config.normalize_color(color),
    }


def write_id3_grouping(file_path, value):
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()
    for key in GROUPING_KEYS:
        tags.delall(key)
    tags.add(TIT1(encoding=3, text=[value]))
    tags.save(file_path)


def write_id3_color(file_path, value):
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()
    for key in COLOR_KEYS:
        tags.delall(key)
    tags.add(TXXX(encoding=3, desc="Color", text=[value]))
    tags.save(file_path)


def clear_id3_grouping(file_path):
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return
    for key in GROUPING_KEYS:
        tags.delall(key)
    tags.save(file_path)


def clear_id3_color(file_path):
    try:
        tags = ID3(file_path)
    except ID3NoHeaderError:
        return
    for key in COLOR_KEYS:
        tags.delall(key)
    tags.save(file_path)
