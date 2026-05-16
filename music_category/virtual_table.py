import re


def clamp_start(start, total, window_size):
    if total <= 0:
        return 0
    return max(0, min(int(start), max(0, total - max(1, window_size))))


def matching_indexes(rows, predicate):
    return [index for index, row in enumerate(rows) if predicate(row)]


def numeric_value(value):
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    return float(match.group(0))


def sort_key(row, column, numeric_columns=None):
    numeric_columns = set(numeric_columns or [])
    value = row.get(column, "")
    is_empty = str(value or "").strip() == ""
    if column in numeric_columns:
        number = numeric_value(value)
        return is_empty or number is None, number if number is not None else 0.0
    return is_empty, str(value or "").casefold()


def sorted_indexes(rows, indexes, column="", direction="none", numeric_columns=None):
    if not column or direction == "none":
        return list(indexes)
    ordered = sorted(
        indexes,
        key=lambda index: (sort_key(rows[index], column, numeric_columns), index),
    )
    if direction != "desc":
        return ordered
    non_empty = [index for index in ordered if not sort_key(rows[index], column, numeric_columns)[0]]
    empty = [index for index in ordered if sort_key(rows[index], column, numeric_columns)[0]]
    return list(reversed(non_empty)) + empty


def next_sort_state(current_column, current_direction, clicked_column):
    if current_column != clicked_column:
        return clicked_column, "asc"
    if current_direction == "asc":
        return clicked_column, "desc"
    if current_direction == "desc":
        return "", "none"
    return clicked_column, "asc"


def visible_slice(indexes, start, window_size):
    start = clamp_start(start, len(indexes), window_size)
    end = min(len(indexes), start + max(1, window_size))
    return start, end, indexes[start:end]


def start_for_row_index(indexes, row_index, current_start, window_size):
    try:
        position = indexes.index(row_index)
    except ValueError:
        return clamp_start(current_start, len(indexes), window_size)
    if current_start <= position < current_start + window_size:
        return clamp_start(current_start, len(indexes), window_size)
    half_window = max(1, window_size // 3)
    return clamp_start(position - half_window, len(indexes), window_size)


def scrollbar_fractions(start, total, window_size):
    if total <= 0:
        return 0.0, 1.0
    first = start / total
    last = min(1.0, (start + max(1, window_size)) / total)
    return first, last
