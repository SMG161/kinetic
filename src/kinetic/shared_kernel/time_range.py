"""TimeRange: the period every membership, designation and coverage is valid for."""

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class TimeRange:
    """Half-open period [start, end). end=None means open-ended: still running.

    Half-open is what makes a handoff clean: one range closes at t and the next
    opens at t, with no gap and no overlap. Postgres tstzrange uses the same rule.
    """

    start: datetime
    end: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.start, "start")
        if self.end is not None:
            _require_aware(self.end, "end")
            if self.end <= self.start:
                raise ValueError(f"end ({self.end}) must be after start ({self.start})")

    @property
    def is_open(self) -> bool:
        return self.end is None

    def contains(self, at: datetime) -> bool:
        return self.start <= at and _before_end(at, self.end)

    def overlaps(self, other: "TimeRange") -> bool:
        return _before_end(self.start, other.end) and _before_end(other.start, self.end)

    def encloses(self, other: "TimeRange") -> bool:
        """True if other lies entirely inside self, e.g. a coverage inside its membership."""
        if other.start < self.start:
            return False
        if self.end is None:
            return True
        return other.end is not None and other.end <= self.end

    def close(self, at: datetime) -> "TimeRange":
        """Return a copy that ends at `at`. Ranges are never edited, only closed."""
        if self.end is not None:
            raise ValueError(f"range is already closed at {self.end}")
        return replace(self, end=at)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _before_end(instant: datetime, end: datetime | None) -> bool:
    return end is None or instant < end
