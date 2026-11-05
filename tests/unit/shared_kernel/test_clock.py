from datetime import UTC, datetime, timedelta

import pytest

from kinetic.shared_kernel import FixedClock, SystemClock

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def test_system_clock_is_timezone_aware():
    assert SystemClock().now().tzinfo is not None


def test_fixed_clock_stands_still_until_advanced():
    clock = FixedClock(T0)
    assert clock.now() == clock.now() == T0
    clock.advance(timedelta(days=14))
    assert clock.now() == T0 + timedelta(days=14)


def test_fixed_clock_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 11, 3))
