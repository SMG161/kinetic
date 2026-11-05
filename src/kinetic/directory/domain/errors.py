class DirectoryError(Exception):
    """Base for directory rule violations."""


class InvalidName(DirectoryError):
    pass


class NotAnOrgManager(DirectoryError):
    """Only an org's owner or admin may change its staff."""


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
