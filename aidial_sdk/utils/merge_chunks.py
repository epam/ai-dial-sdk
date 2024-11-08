import copy
from typing import Any, List, TypeVar, Union, cast

T = TypeVar("T")

Path = List[Union[int, str]]


LIST_OF_DICTS_ERROR_MESSAGE = (
    "Lists could be merged only if their elements are dictionaries"
)

INDEX_ERROR_MESSAGE = "A list element must have 'index' field to identify position of the element in the list"

INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE = (
    "All elements of a list must be either indexed or not indexed"
)

CANNOT_MERGE_NON_INDEXED_LISTS_ERROR_MESSAGE = (
    "Cannot merge two non-indexed non-empty lists"
)

CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE = (
    "Cannot merge a non-indexed list with an indexed list"
)


def show_json_path(path: Path) -> str:
    ret = "$"
    for elem in path:
        if isinstance(elem, int):
            ret += f"[{elem}]"
        else:
            ret += f".{elem}"
    return ret


def merge_str(target: str, source: str, path: Path) -> str:
    return target + source


def merge_int(target: int, source: int, path: Path) -> int:
    return source


def merge_float(target: float, source: float, path: Path) -> float:
    return source


def merge_bool(target: bool, source: bool, path: Path) -> bool:
    return source


def merge_dicts(target: dict, source: dict, path: Path) -> dict:
    for key, value in source.items():
        path.append(key)
        target[key] = merge_recursive(target.get(key), value, path)
        path.pop()

    return target


def is_indexed_list(xs: list) -> bool:
    if len(xs) == 0:
        return False

    all_indexed = True
    any_indexed = False
    for elem in xs:
        if isinstance(elem, dict) and "index" in elem:
            any_indexed = True
        else:
            all_indexed = False

    if any_indexed and not all_indexed:
        raise AssertionError(INCONSISTENT_INDEXED_LIST_ERROR_MESSAGE)

    return all_indexed


def merge_indexed_lists(target: list, source: list, path: Path) -> list:
    for elem in source:
        assert isinstance(elem, dict), LIST_OF_DICTS_ERROR_MESSAGE

        index = elem.get("index")
        assert isinstance(index, int), INDEX_ERROR_MESSAGE

        path.append(index)

        if index < len(target):
            target[index] = merge_recursive(target[index], elem, path)
        else:
            target.extend([{"index": idx} for idx in range(len(target), index)])
            target.append(copy.deepcopy(elem))

        path.pop()

    return target


def merge_lists(target: list, source: list, path: Path) -> list:
    is_target_indexed = is_indexed_list(target)
    is_source_indexed = is_indexed_list(source)

    if len(source) == 0:
        return target

    if len(target) == 0:
        if is_source_indexed:
            return merge_indexed_lists(target, source, path)
        else:
            return copy.deepcopy(source)

    if not is_target_indexed and not is_source_indexed:
        raise AssertionError(CANNOT_MERGE_NON_INDEXED_LISTS_ERROR_MESSAGE)

    assert (
        is_target_indexed and is_source_indexed
    ), CANNOT_MERGE_NON_INDEXED_AND_INDEXED_LISTS_ERROR_MESSAGE

    return merge_indexed_lists(target, source, path)


def merge_recursive(target: T, source: Any, path: Path) -> T:
    """
    Recursively merging content of the source object into the target object.
    The target object is modified in-place.
    The source object is left unmodified.
    """

    if source is None:
        return target

    if target is None:
        if isinstance(source, dict):
            target = cast(T, {})
        elif isinstance(source, list):
            target = cast(T, [])
        else:
            return source

    if isinstance(target, list) and isinstance(source, list):
        return merge_lists(target, source, path)
    elif isinstance(target, dict) and isinstance(source, dict):
        return merge_dicts(target, source, path)
    elif isinstance(target, int) and isinstance(source, int):
        return merge_int(target, source, path)
    elif isinstance(target, float) and isinstance(source, float):
        return merge_float(target, source, path)
    elif isinstance(target, bool) and isinstance(source, bool):
        return merge_bool(target, source, path)
    elif isinstance(target, str) and isinstance(source, str):
        return merge_str(target, source, path)

    raise TypeError(
        f"Cannot merge '{type(target).__name__}' with incoming '{type(source).__name__}' at path {show_json_path(path)}"
    )


def merge(*chunks: T) -> T:
    """
    Merge a list of chunks into one.
    The very first chunk is modified in-place by accumulating the content of the subsequent chunks.
    The subsequent chunks aren't modified.
    The new content added to the first chunk is deeply copied from a source chunk.
    """

    assert len(chunks) > 0, "At least one chunk must be provided"
    ret: T = chunks[0]
    for chunk in chunks[1:]:
        ret = merge_recursive(ret, chunk, path=[])
    return ret


def cleanup_indices(chunk: T) -> T:
    """
    Recursively remove all "index" fields inside list elements in the given chunk.
    The chunk is modified in-place.
    """

    if isinstance(chunk, list):
        ret = []
        for elem in chunk:
            if isinstance(elem, dict) and "index" in elem:
                elem = elem.copy()
                del elem["index"]
            ret.append(cleanup_indices(elem))
        return cast(T, ret)

    if isinstance(chunk, dict):
        return cast(
            T, {key: cleanup_indices(value) for key, value in chunk.items()}
        )

    return chunk


_Chunk = TypeVar("_Chunk", bound=dict)


def merge_chat_completion_chunks(*chunks: _Chunk) -> _Chunk:
    """
    The recursive merging procedure that avoids merging top-level atomic fields
    (e.g. "id", "created", "model", "object", "system_fingerprint") and
    instead chooses an _override_ merging strategy for such fields.
    Non-atomic fields (e.g. "choice", "usage") are merged following
    the standard recursive merging procedure.

    The very first chunk is modified in-place.
    The subsequent chunks are left unmodified.
    """

    assert (
        len(chunks) > 0
    ), "At least one chat completion chunk must be provided"

    assert all(
        isinstance(chunk, dict) for chunk in chunks
    ), "The chat completion chunks are expected to be dictionaries"

    target, *sources = chunks

    for chunk in sources:
        source = cast(_Chunk, chunk.copy())
        for key, value in list(source.items()):
            if not isinstance(value, (list, dict)) and value is not None:
                target[key] = value
                del source[key]
        target = merge(target, source)

    return target
