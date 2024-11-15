import itertools
import timeit
from typing import Iterable, List

from pydantic import BaseModel

from aidial_sdk.utils.merge_chunks import merge_chat_completion_chunks
from tests.utils.chunks import create_chunk


def _interleave(*iters):
    sentinel = object()
    return [
        elem
        for tpl in itertools.zip_longest(*iters, fillvalue=sentinel)
        for elem in tpl
        if elem is not sentinel
    ]


class ChunkGenerator(BaseModel):
    n_choices: int = 1
    n_chunks_per_choice: int = 1
    reversed_choices: bool = False
    n_attachments_per_choice: int = 0
    reversed_attachments: bool = False

    @property
    def desc(self) -> str:
        r1 = "r" if self.reversed_choices else ""
        r2 = "r" if self.reversed_attachments else ""
        return f"{self.n_choices}{r1}x({self.n_chunks_per_choice}+{self.n_attachments_per_choice}{r2})"

    def get_stream(self) -> Iterable[dict]:
        def _range(n: int, rev: bool):
            return reversed(range(n)) if rev else range(n)

        def gen_content(choice_idx: int):
            for chunk_idx in range(self.n_chunks_per_choice):
                yield create_chunk(
                    choice_idx=choice_idx,
                    delta={"content": f"{chunk_idx} "},
                )

        def gen_attachments(choice_idx: int):
            for attachment_idx in _range(
                self.n_attachments_per_choice, self.reversed_attachments
            ):
                yield create_chunk(
                    choice_idx=choice_idx,
                    delta={
                        "custom_content": {
                            "attachments": [
                                {
                                    "index": attachment_idx,
                                    "url": f"url{attachment_idx}",
                                }
                            ]
                        }
                    },
                )

        yield create_chunk(delta={"role": "assistant", "content": None})

        for choice_idx in _range(self.n_choices, self.reversed_choices):
            yield from _interleave(
                gen_content(choice_idx),
                gen_attachments(choice_idx),
            )

            yield create_chunk(choice_idx=choice_idx, finish_reason="stop")


def benchmark(gen: ChunkGenerator, *, repeat: int, number: int | None = None):
    def stmt():
        merge_chat_completion_chunks({}, *gen.get_stream())

    t = timeit.Timer(stmt=stmt)

    if number is None:
        number, _ = t.autorange()

    timings = t.repeat(number=number, repeat=repeat)

    best_sec = min(timings) / number
    best_msec = best_sec * 1e3
    best_usec = best_sec * 1e6

    n_chunks = len(list(gen.get_stream()))

    print(
        ",".join(
            [
                gen.desc,
                str(n_chunks),
                str(number),
                str(repeat),
                f"{best_sec:.3f}",
                f"{best_msec:.3f}",
                f"{best_usec:.3f}",
            ]
        )
    )


base_case = ChunkGenerator(
    n_choices=10,
    reversed_choices=False,
    n_chunks_per_choice=10,
    n_attachments_per_choice=10,
    reversed_attachments=False,
)

one_choice = base_case.model_copy(update={"n_choices": 1})

cases: List[ChunkGenerator] = [
    base_case,
    base_case.model_copy(update={"n_choices": 20}),
    base_case.model_copy(update={"n_chunks_per_choice": 20}),
    base_case.model_copy(update={"n_attachments_per_choice": 20}),
    base_case.model_copy(update={"reversed_choices": True}),
    base_case.model_copy(update={"reversed_attachments": True}),
    base_case.model_copy(
        update={"reversed_choices": True, "reversed_attachments": True}
    ),
    one_choice.model_copy(
        update={"n_chunks_per_choice": 0, "n_attachments_per_choice": 200}
    ),
    one_choice.model_copy(
        update={"n_chunks_per_choice": 0, "n_attachments_per_choice": 400}
    ),
    one_choice.model_copy(
        update={"n_chunks_per_choice": 200, "n_attachments_per_choice": 0}
    ),
    one_choice.model_copy(
        update={"n_chunks_per_choice": 400, "n_attachments_per_choice": 0}
    ),
]

if __name__ == "__main__":
    print("Description,N chunks,Number,Repeats,Best sec,Best msec,Best usec")
    for gen in cases:
        benchmark(gen, repeat=10)
