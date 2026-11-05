"""Shared kernel: the few concepts every context agrees on (ids, Clock, TimeRange, DomainEvent).

Keep this tiny. Anything added here couples every context to it.
"""

from kinetic.shared_kernel.clock import Clock, FixedClock, SystemClock
from kinetic.shared_kernel.ids import PersonId, new_person_id
from kinetic.shared_kernel.time_range import TimeRange

__all__ = ["Clock", "FixedClock", "PersonId", "SystemClock", "TimeRange", "new_person_id"]
