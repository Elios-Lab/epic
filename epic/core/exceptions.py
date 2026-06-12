"""Exception hierarchy for EPIC Core."""


class EPICError(Exception):
    """Base class for all EPIC exceptions."""


# --- Plugin errors ---


class PluginError(EPICError):
    """Base class for plugin-related errors."""


class PluginValidationError(PluginError):
    """Raised when a plugin fails interface validation at registration."""


class DuplicatePluginError(PluginError):
    """Raised when a plugin with the same id+version is already registered."""


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin id/version is not in the registry."""


class PluginExecutionError(PluginError):
    """
    Raised when a plugin method raises an unexpected exception.
    Wraps the original exception as __cause__.
    """


# --- Simulation errors ---


class SimulationError(EPICError):
    """Base class for simulation errors."""


class SessionNotFoundError(SimulationError):
    """Raised when a session_id does not exist."""


class SessionStateError(SimulationError):
    """Raised when an operation is invalid for the session's current state."""


# --- Domain errors ---


class ContestError(EPICError):
    """Base class for contest-related errors."""


class ContestNotFoundError(ContestError):
    pass


class ContestStateError(ContestError):
    """Raised when an operation is invalid for the contest's lifecycle state."""


class RegistrationError(ContestError):
    pass


class SubmissionError(ContestError):
    pass


class EvaluationPendingError(ContestError):
    """
    Raised by a TaskEvaluator when the evaluation window is not yet fully
    populated with observations. Control-flow signal: the submission stays
    PENDING and scoring is retried later. Never exposed through the API.
    """


# --- Auth errors ---


class AuthError(EPICError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InsufficientPermissionsError(AuthError):
    pass


# --- Validation errors ---


class EPICValidationError(EPICError):
    """Raised when request data fails business-rule validation."""
