from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from kinetic.shared_kernel import TimeRange

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def r(start: int, end: int | None = None) -> TimeRange:
    """Range from day `start` to day `end` (None = open-ended)."""
    return TimeRange(day(start), None if end is None else day(end))


class TestConstruction:
    def test_open_ended_range_is_open(self):
        assert r(0).is_open
        assert not r(0, 5).is_open

    @pytest.mark.parametrize("end", [0, -1])
    def test_end_must_be_after_start(self, end):
        with pytest.raises(ValueError):
            r(0, end)

    def test_naive_datetimes_are_rejected(self):
        with pytest.raises(ValueError):
            TimeRange(datetime(2026, 11, 3))

    def test_is_immutable(self):
        with pytest.raises(FrozenInstanceError):
            r(0).end = day(5)


class TestContains:
    def test_start_is_included(self):
        assert r(0, 5).contains(day(0))

    def test_end_is_excluded(self):
        assert not r(0, 5).contains(day(5))

    def test_before_start_is_excluded(self):
        assert not r(0, 5).contains(day(-1))

    def test_open_ended_contains_far_future(self):
        assert r(0).contains(day(10_000))


class TestOverlaps:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            (r(0, 5), r(5, 10), False),  # adjacent: a handoff at day 5
            (r(0, 5), r(6, 10), False),  # disjoint
            (r(0, 5), r(4, 10), True),  # partial
            (r(0, 10), r(2, 3), True),  # one inside the other
            (r(0), r(100, 101), True),  # open-ended runs into the future
            (r(0), r(5), True),  # two open-ended ranges
            (r(5), r(0, 5), False),  # open-ended starts where the other ends
        ],
    )
    def test_overlaps_is_symmetric(self, a, b, expected):
        assert a.overlaps(b) is expected
        assert b.overlaps(a) is expected


class TestEncloses:
    @pytest.mark.parametrize(
        ("outer", "inner", "expected"),
        [
            (r(0, 30), r(10, 24), True),  # two-week cover inside the membership
            (r(0, 30), r(0, 30), True),  # identical
            (r(0), r(10, 24), True),  # open-ended membership
            (r(0), r(10), True),
            (r(5, 30), r(0, 10), False),  # starts before
            (r(0, 30), r(20, 40), False),  # ends after
            (r(0, 30), r(10), False),  # open-ended cover, closed membership
        ],
    )
    def test_encloses(self, outer, inner, expected):
        assert outer.encloses(inner) is expected


class TestClose:
    def test_close_returns_a_new_closed_range_and_leaves_the_original(self):
        original = r(0)
        closed = original.close(day(5))
        assert closed == r(0, 5)
        assert original.is_open

    def test_cannot_close_twice(self):
        with pytest.raises(ValueError):
            r(0, 5).close(day(6))

    def test_cannot_close_at_or_before_start(self):
        with pytest.raises(ValueError):
            r(0).close(day(0))

    def test_handoff_leaves_no_gap_and_no_overlap(self):
        old = r(0).close(day(5))
        new = TimeRange(day(5))
        assert not old.overlaps(new)
        assert not old.contains(day(5)) and new.contains(day(5))
