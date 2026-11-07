class DirectoryError(Exception):
    """Base for directory rule violations."""


class InvalidName(DirectoryError):
    pass


class NotAnOrgManager(DirectoryError):
    """Only an org's owner or admin may change its staff or client relationships."""


class NotOrgStaff(DirectoryError):
    """The person holds no role at this org."""


class InvalidStaffRole(DirectoryError):
    pass


class AlreadyStaff(DirectoryError):
    pass


class NoDisciplines(DirectoryError):
    pass


class NotQualified(DirectoryError):
    """A practitioner may only practise disciplines their provider profile is qualified in."""


class AlreadyRegistered(DirectoryError):
    """The person already has this kind of profile."""


class NotFound(DirectoryError):
    pass


class AlreadyServed(DirectoryError):
    """The org already has an active relationship with this client."""


class InvalidPracticeLead(DirectoryError):
    """The lead must be the org's staff, must not be the client, and must actually change on handoff."""


class InvalidReason(DirectoryError):
    pass


class InvalidTiming(DirectoryError):
    """A change must come after what it changes."""


class InvitationUnusable(DirectoryError):
    """Already accepted or expired."""


class InvitationNotForYou(DirectoryError):
    """The signed-in person's email is not the one the invitation was sent to."""


class ConcurrentChange(DirectoryError):
    """Someone else changed the same thing at the same moment; retry with fresh data."""
