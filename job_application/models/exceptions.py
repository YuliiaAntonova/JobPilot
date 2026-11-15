"""Business errors mapped to HTTP in routers."""


class ApplicationError(Exception):
    pass


class JobNotFound(ApplicationError):
    pass


class InvalidJobState(ApplicationError):
    pass


class ResumeMissing(ApplicationError):
    pass


class ArtifactNotFound(ApplicationError):
    pass


class InvalidApplicationForm(ApplicationError):
    pass
