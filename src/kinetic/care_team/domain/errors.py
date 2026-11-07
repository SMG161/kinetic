class CareTeamError(Exception):
    """Base for care team rule violations."""


class InvalidReason(CareTeamError):
    pass


class SelfTreatment(CareTeamError):
    """A client is never a member of, nor a cover on, their own care team."""


class InvalidOrgContext(CareTeamError):
    """The org does not employ the provider in that discipline, or does not serve the client."""


class NotQualified(CareTeamError):
    pass


class AlreadyOnTeam(CareTeamError):
    """A provider never has two overlapping memberships on the same team."""


class InvalidEngagement(CareTeamError):
    pass


class NotFound(CareTeamError):
    pass


class InvalidTiming(CareTeamError):
    """A change must come after what it changes, and a window must make sense."""


class InvalidCoverage(CareTeamError):
    pass


class TeamAlreadyExists(CareTeamError):
    """One care team per client: another request created this client's team first."""


class ConcurrentChange(CareTeamError):
    """Someone else changed the team since it was loaded. Reload and try again."""
