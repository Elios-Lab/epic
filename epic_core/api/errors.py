"""Global API error handling."""

import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from epic_core.kernel.exceptions import (
    ContestNotFoundError,
    ContestStateError,
    EPICError,
    EPICValidationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    PluginExecutionError,
    PluginNotFoundError,
    PluginValidationError,
    RegistrationError,
    SessionNotFoundError,
    SessionStateError,
    SubmissionError,
)


def error_content(exc: EPICError, debug: bool = False) -> dict:
    """Build the standard error envelope; include the traceback on server
    errors when debug mode is enabled (never in production)."""
    content = {"error": {"code": error_to_code(exc), "message": str(exc)}}
    if debug and error_to_status_code(exc) >= 500:
        content["error"]["traceback"] = traceback.format_exception(exc)
    return content


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EPICError)
    async def epic_error_handler(request: Request, exc: EPICError):
        settings = getattr(request.app.state, "settings", None)
        debug = bool(settings.debug) if settings is not None else False
        return JSONResponse(
            status_code=error_to_status_code(exc),
            content=error_content(exc, debug),
        )


def error_to_status_code(exc: EPICError) -> int:
    if isinstance(exc, PluginNotFoundError):
        return 404
    if isinstance(exc, SessionNotFoundError):
        return 404
    if isinstance(exc, ContestNotFoundError):
        return 404
    if isinstance(exc, ContestStateError):
        return 409
    if isinstance(exc, SessionStateError):
        return 409
    if isinstance(exc, RegistrationError):
        return 409
    if isinstance(exc, SubmissionError):
        return 422
    if isinstance(exc, EPICValidationError):
        return 422
    if isinstance(exc, InvalidCredentialsError):
        return 401
    if isinstance(exc, InsufficientPermissionsError):
        return 403
    if isinstance(exc, PluginValidationError):
        return 500
    if isinstance(exc, PluginExecutionError):
        return 500
    return 500


def error_to_code(exc: EPICError) -> str:
    if isinstance(exc, PluginNotFoundError):
        return "PLUGIN_NOT_FOUND"
    if isinstance(exc, SessionNotFoundError):
        return "SESSION_NOT_FOUND"
    if isinstance(exc, ContestNotFoundError):
        return "CONTEST_NOT_FOUND"
    if isinstance(exc, ContestStateError):
        return "CONTEST_STATE_ERROR"
    if isinstance(exc, SessionStateError):
        return "SESSION_STATE_ERROR"
    if isinstance(exc, RegistrationError):
        return "REGISTRATION_ERROR"
    if isinstance(exc, SubmissionError):
        return "SUBMISSION_ERROR"
    if isinstance(exc, EPICValidationError):
        return "VALIDATION_ERROR"
    if isinstance(exc, InvalidCredentialsError):
        return "INVALID_CREDENTIALS"
    if isinstance(exc, InsufficientPermissionsError):
        return "FORBIDDEN"
    if isinstance(exc, PluginValidationError):
        return "PLUGIN_VALIDATION_ERROR"
    if isinstance(exc, PluginExecutionError):
        return "PLUGIN_EXECUTION_ERROR"
    return "INTERNAL_ERROR"

