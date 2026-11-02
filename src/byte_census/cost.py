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
from types import MappingProxyType

from byte_census.model import Cost

SUBPROCESS_READ_NOTE = (
    "Reads performed inside external commands cannot be measured from this process."
)
COUNTER_FIELDS = (
    "content_bytes_read",
    "entries_visited",
    "subprocess_calls",
    "subprocess_stdout_bytes",
)

Clock = Callable[[], float]


def _check_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError(f"counter amount must be a non-negative integer: {amount!r}")


def _plus(current: int | None, amount: int) -> int | None:
    return None if current is None else current + amount


@dataclass(frozen=True)
class CostCounters:
    """Work counters for one process; every update returns a new object."""

    content_bytes_read: int | None = 0
    entries_visited: int | None = 0
    subprocess_calls: int | None = 0
    subprocess_stdout_bytes: int | None = 0
    note_items: tuple[tuple[str, str], ...] = ()

    @property
    def notes(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.note_items))

    def _add(self, name: str, amount: int) -> "CostCounters":
        _check_amount(amount)
        return replace(self, **{name: _plus(getattr(self, name), amount)})

    def add_content_bytes(self, amount: int) -> "CostCounters":
        """Bytes returned by byte-census's own content reads."""
        return self._add("content_bytes_read", amount)

    def add_entries(self, amount: int) -> "CostCounters":
        """Directory entries examined (lstat or scandir entries)."""
        return self._add("entries_visited", amount)

    def add_subprocess_call(self, stdout_bytes: int) -> "CostCounters":
        """One runner call, successful or not, with its captured stdout size."""
        return self._add("subprocess_calls", 1)._add(
            "subprocess_stdout_bytes", stdout_bytes
        )

    def unmeasured(self, name: str, note: str) -> "CostCounters":
        """Mark a counter as not measurable: null with a note, never zero."""
        if name not in COUNTER_FIELDS:
            raise ValueError(f"unknown cost counter: {name!r}")
        notes = {**self.notes, name: note}
        return replace(self, **{name: None}, note_items=tuple(sorted(notes.items())))

    def merge(self, other: "CostCounters") -> "CostCounters":
        """Sum two processes' counters; a null on either side stays null."""
        values = {
            name: None
            if getattr(self, name) is None or getattr(other, name) is None
            else getattr(self, name) + getattr(other, name)
            for name in COUNTER_FIELDS
        }
        notes = {**other.notes, **self.notes}
        return CostCounters(**values, note_items=tuple(sorted(notes.items())))


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
