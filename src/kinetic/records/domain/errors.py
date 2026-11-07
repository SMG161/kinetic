class RecordsError(Exception):
    """Base for records rule violations."""


class InvalidBody(RecordsError):
    pass
