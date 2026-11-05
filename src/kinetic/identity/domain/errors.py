class IdentityError(Exception):
    """Base for identity rule violations."""


class InvalidEmail(IdentityError):
    pass


class WeakPassword(IdentityError):
    pass


class EmailAlreadyRegistered(IdentityError):
    pass


class InvalidCredentials(IdentityError):
    """Deliberately vague: never reveal whether the email or the password was wrong."""


class InvalidAccessToken(IdentityError):
    pass


class InvalidRefreshToken(IdentityError):
    pass
