INDEX_ERROR_MESSAGE = "A list element must have 'index' field to identify position of the element in the list"

INDEX_INTEGER_ERROR_MESSAGE = (
    "A list element must have 'index' field of a integer type, but got {ty}"
)

INDEX_NON_NEGATIVE_ERROR_MESSAGE = "A list element must have 'index' field which a non-negative integer, but got {index}"

INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE = (
    "All elements of a list must be either indexed or not indexed"
)


def try_parse_indexed_list(
    xs: list, *, normalize_inplace: bool = False
) -> bool:
    if len(xs) == 0:
        return False

    all_indexed = True
    max_index = None
    normalized = True

    for idx, elem in enumerate(xs):
        if isinstance(elem, dict) and (index := elem.get("index")) is not None:
            if not isinstance(index, int):
                raise AssertionError(
                    INDEX_INTEGER_ERROR_MESSAGE.format(ty=type(index).__name__)
                )

            if index < 0:
                raise AssertionError(
                    INDEX_NON_NEGATIVE_ERROR_MESSAGE.format(index=index)
                )

            normalized = normalized and idx == index

            max_index = index if max_index is None else max(max_index, index)
        else:
            all_indexed = False

    if max_index is not None and not all_indexed:
        raise AssertionError(INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE)

    if max_index is None:
        return False

    if not normalized and normalize_inplace:
        _normalize_indexed_list(xs, max_index + 1)

    return True


def _normalize_indexed_list(xs: list, new_length: int) -> list:
    elems = {elem.get("index"): elem for elem in xs}

    xs.clear()
    for index in range(new_length):
        elem = elems.pop(index, None)
        if elem is not None:
            xs.append(elem)
        else:
            xs.append({"index": index})

    return xs
