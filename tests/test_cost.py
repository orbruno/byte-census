"""Cost meter and counters (WI-CORE AC-03)."""

import dataclasses
import pickle

import pytest

from byte_census.cost import (
    SUBPROCESS_READ_NOTE,
    CostCounters,
    CostMeter,
    sum_counters,
)
from byte_census.model import Cost


def fake_clock(*values: float):
    iterator = iter(values)
    return lambda: next(iterator)


def test_counters_start_at_zero() -> None:
    counters = CostCounters()

    assert (
        counters.content_bytes_read,
        counters.entries_visited,
        counters.subprocess_calls,
        counters.subprocess_stdout_bytes,
    ) == (0, 0, 0, 0)


def test_counter_updates_return_new_objects() -> None:
    base = CostCounters()

    after = base.add_content_bytes(10).add_entries(3).add_subprocess_call(42)

    assert base == CostCounters()
    assert after.content_bytes_read == 10
    assert after.entries_visited == 3
    assert after.subprocess_calls == 1
    assert after.subprocess_stdout_bytes == 42
    with pytest.raises(dataclasses.FrozenInstanceError):
        after.entries_visited = 0  # type: ignore[misc]


@pytest.mark.parametrize("amount", [-1, 1.5, True])
def test_counter_rejects_bad_amounts(amount: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        CostCounters().add_entries(amount)  # type: ignore[arg-type]


def test_counters_from_several_processes_are_summed() -> None:
    workers = [
        CostCounters().add_entries(5).add_content_bytes(100),
        CostCounters().add_entries(7).add_subprocess_call(3),
        CostCounters().add_entries(1),
    ]
    shipped = [pickle.loads(pickle.dumps(worker)) for worker in workers]

    total = sum_counters(shipped)

    assert total.entries_visited == 13
    assert total.content_bytes_read == 100
    assert total.subprocess_calls == 1
    assert total.subprocess_stdout_bytes == 3
    assert sum_counters([]) == CostCounters()


def test_unmeasured_counter_is_null_with_note_and_stays_null_when_merged() -> None:
    blind = CostCounters().unmeasured("entries_visited", "walker crashed")

    merged = blind.merge(CostCounters().add_entries(10))

    assert merged.entries_visited is None
    assert merged.notes == {"entries_visited": "walker crashed"}
    assert merged.add_entries(1).entries_visited is None


def test_unmeasured_rejects_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown"):
        CostCounters().unmeasured("elapsed_s", "x")


def test_meter_measures_elapsed_once_and_rounds_to_ms() -> None:
    meter = CostMeter.start(fake_clock(100.0, 101.23456))

    cost = meter.finish(CostCounters())

    assert cost.elapsed_s == 1.235


def test_meter_without_subprocess_reports_zero_subprocess_reads() -> None:
    cost = CostMeter.start(fake_clock(0.0, 0.5)).finish(
        CostCounters().add_entries(4).add_content_bytes(9)
    )

    assert cost.to_dict() == {
        "elapsed_s": 0.5,
        "content_bytes_read": 9,
        "entries_visited": 4,
        "subprocess_calls": 0,
        "subprocess_stdout_bytes": 0,
        "subprocess_content_bytes_read": 0,
        "notes": {},
    }


def test_meter_with_subprocess_reports_null_reads_with_note() -> None:
    cost = CostMeter.start(fake_clock(0.0, 2.0)).finish(
        CostCounters().add_subprocess_call(10).add_subprocess_call(0)
    )

    assert cost.subprocess_calls == 2
    assert cost.subprocess_stdout_bytes == 10
    assert cost.subprocess_content_bytes_read is None
    assert cost.notes == {"subprocess_content_bytes_read": SUBPROCESS_READ_NOTE}


def test_meter_carries_unmeasured_counter_notes() -> None:
    counters = CostCounters().unmeasured("content_bytes_read", "worker lost")

    cost = CostMeter.start(fake_clock(0.0, 1.0)).finish(counters)

    assert cost.content_bytes_read is None
    assert cost.notes == {"content_bytes_read": "worker lost"}


def test_cost_requires_a_note_for_every_null() -> None:
    with pytest.raises(ValueError, match="note"):
        Cost(0.1, None, 0, 0, 0, 0, {})


def test_cost_rejects_notes_for_measured_fields() -> None:
    with pytest.raises(ValueError, match="note"):
        Cost(0.1, 0, 0, 0, 0, 0, {"entries_visited": "x"})


def test_cost_notes_are_read_only() -> None:
    cost = Cost(0.1, 0, 0, 1, 0, None, {"subprocess_content_bytes_read": "n"})

    with pytest.raises(TypeError):
        cost.notes["x"] = "y"  # type: ignore[index]


def test_counters_reject_null_without_note() -> None:
    with pytest.raises(ValueError, match="note"):
        CostCounters(entries_visited=None)


def test_counters_reject_note_for_measured_field() -> None:
    with pytest.raises(ValueError, match="note"):
        CostCounters(note_items=(("entries_visited", "x"),))


def test_counters_with_null_and_note_are_valid_and_hashable() -> None:
    counters = CostCounters(
        entries_visited=None, note_items=(("entries_visited", "x"),)
    )

    assert counters.notes == {"entries_visited": "x"}
    assert hash(counters) == hash(pickle.loads(pickle.dumps(counters)))


@pytest.mark.parametrize("field", ["content_bytes_read", "subprocess_calls"])
def test_unmeasured_works_for_every_counter(field: str) -> None:
    counters = CostCounters().unmeasured(field, "lost")

    assert counters.notes == {field: "lost"}
