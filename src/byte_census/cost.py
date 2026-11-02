"""Cost meter for `meta.cost` (docs/contracts/quantities.md, WI-CORE AC-03).

`CostCounters` is an immutable, picklable bundle of work counters. Workers in
other processes return their own counters and the caller sums them with
`sum_counters`. A counter that could not be measured is `None` with a note,
and stays `None` after merging. `CostMeter` holds the single wall-clock start;
`elapsed_s` is never a sum.
"""

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from byte_census.model import Cost, FrozenMap, check_null_notes

SUBPROCESS_READ_NOTE = (
    "Reads performed inside external commands cannot be measured from this process."
)
Clock = Callable[[], float]


def _check_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError(f"counter amount must be a non-negative integer: {amount!r}")


def _plus(current: int | None, amount: int) -> int | None:
    return None if current is None else current + amount


def _sum(left: int | None, right: int | None) -> int | None:
    return None if left is None or right is None else left + right


def _note_items(notes: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(notes.items()))


@dataclass(frozen=True)
class CostCounters:
    """Work counters for one process; every update returns a new object."""

    content_bytes_read: int | None = 0
    entries_visited: int | None = 0
    subprocess_calls: int | None = 0
    subprocess_stdout_bytes: int | None = 0
    note_items: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        check_null_notes(self.values(), self.notes)

    @property
    def notes(self) -> Mapping[str, str]:
        return FrozenMap(self.note_items)

    def values(self) -> dict[str, int | None]:
        """The counters by name."""
        return {
            "content_bytes_read": self.content_bytes_read,
            "entries_visited": self.entries_visited,
            "subprocess_calls": self.subprocess_calls,
            "subprocess_stdout_bytes": self.subprocess_stdout_bytes,
        }

    def add_content_bytes(self, amount: int) -> "CostCounters":
        """Bytes returned by byte-census's own content reads."""
        _check_amount(amount)
        return replace(self, content_bytes_read=_plus(self.content_bytes_read, amount))

    def add_entries(self, amount: int) -> "CostCounters":
        """Directory entries examined (lstat or scandir entries)."""
        _check_amount(amount)
        return replace(self, entries_visited=_plus(self.entries_visited, amount))

    def add_subprocess_call(self, stdout_bytes: int) -> "CostCounters":
        """One runner call, successful or not, with its captured stdout size."""
        _check_amount(stdout_bytes)
        return replace(
            self,
            subprocess_calls=_plus(self.subprocess_calls, 1),
            subprocess_stdout_bytes=_plus(self.subprocess_stdout_bytes, stdout_bytes),
        )

    def unmeasured(self, name: str, note: str) -> "CostCounters":
        """Mark a counter as not measurable: null with a note, never zero."""
        if name not in _UNMEASURED:
            raise ValueError(f"unknown cost counter: {name!r}")
        return _UNMEASURED[name](self, _note_items({**self.notes, name: note}))

    def merge(self, other: "CostCounters") -> "CostCounters":
        """Sum two processes' counters; a null on either side stays null."""
        return CostCounters(
            content_bytes_read=_sum(self.content_bytes_read, other.content_bytes_read),
            entries_visited=_sum(self.entries_visited, other.entries_visited),
            subprocess_calls=_sum(self.subprocess_calls, other.subprocess_calls),
            subprocess_stdout_bytes=_sum(
                self.subprocess_stdout_bytes, other.subprocess_stdout_bytes
            ),
            note_items=_note_items({**other.notes, **self.notes}),
        )


Notes = tuple[tuple[str, str], ...]
_UNMEASURED: Mapping[str, Callable[[CostCounters, Notes], CostCounters]] = {
    "content_bytes_read": lambda c, n: replace(
        c, content_bytes_read=None, note_items=n
    ),
    "entries_visited": lambda c, n: replace(c, entries_visited=None, note_items=n),
    "subprocess_calls": lambda c, n: replace(c, subprocess_calls=None, note_items=n),
    "subprocess_stdout_bytes": lambda c, n: replace(
        c, subprocess_stdout_bytes=None, note_items=n
    ),
}


def sum_counters(parts: Iterable[CostCounters]) -> CostCounters:
    """Sum counters from any number of processes."""
    total = CostCounters()
    for part in parts:
        total = total.merge(part)
    return total


@dataclass(frozen=True)
class CostMeter:
    """One wall-clock measurement from command start to `finish`."""

    started: float
    clock: Clock = time.monotonic

    @classmethod
    def start(cls, clock: Clock = time.monotonic) -> "CostMeter":
        return cls(started=clock(), clock=clock)

    def finish(self, counters: CostCounters) -> Cost:
        """Build `meta.cost`; reads by subprocesses are null when any ran."""
        elapsed = round(self.clock() - self.started, 3)
        notes = dict(counters.notes)
        if counters.subprocess_calls == 0:
            subprocess_reads: int | None = 0
        else:
            subprocess_reads = None
            notes["subprocess_content_bytes_read"] = SUBPROCESS_READ_NOTE
        return Cost(
            elapsed_s=elapsed,
            content_bytes_read=counters.content_bytes_read,
            entries_visited=counters.entries_visited,
            subprocess_calls=counters.subprocess_calls,
            subprocess_stdout_bytes=counters.subprocess_stdout_bytes,
            subprocess_content_bytes_read=subprocess_reads,
            notes=notes,
        )
