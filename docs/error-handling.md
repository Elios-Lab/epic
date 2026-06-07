# Error Handling

> Related: [Architecture](architecture.md) · [Simulation Engine](simulation-engine.md) · [API Specification](api-specification.md)

This document defines the exception hierarchy, error propagation rules, and the mapping from exceptions to API error responses.

The primary goal is to guarantee that plugin errors never crash the application and that the API always returns a structured, consistent error response.

---

# Design Principles

Plugin failures must be isolated. A faulty sensor or digital twin must not bring down a running session or affect other sessions.

All errors exposed to API clients must use the standard error format defined in [API Specification](api-specification.md).

Internal implementation details (stack traces, database errors) must never be exposed to API clients in production.

---

# Exception Hierarchy

All EPIC exceptions inherit from a common base:

```python
# epic_core/exceptions.py

class EPICError(Exception):
    """Base class for all EPIC exceptions."""
    pass


# --- Plugin errors ---

class PluginError(EPICError):
    """Base class for plugin-related errors."""
    pass

class PluginValidationError(PluginError):
    """Raised when a plugin fails interface validation at registration."""
    pass

class DuplicatePluginError(PluginError):
    """Raised when a plugin with the same id+version is already registered."""
    pass

class PluginNotFoundError(PluginError):
    """Raised when a requested plugin id/version is not in the registry."""
    pass

class PluginExecutionError(PluginError):
    """
    Raised when a plugin method raises an unexpected exception.
    Wraps the original exception as __cause__.
    """
    pass


# --- Simulation errors ---

class SimulationError(EPICError):
    """Base class for simulation errors."""
    pass

class SessionNotFoundError(SimulationError):
    """Raised when a session_id does not exist."""
    pass

class SessionStateError(SimulationError):
    """Raised when an operation is invalid for the session's current state."""
    pass


# --- Domain errors ---

class ContestError(EPICError):
    """Base class for contest-related errors."""
    pass

class ContestNotFoundError(ContestError):
    pass

class ContestStateError(ContestError):
    """Raised when an operation is invalid for the contest's lifecycle state."""
    pass

class RegistrationError(ContestError):
    pass

class SubmissionError(ContestError):
    pass


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
    pass
```

---

# Error Propagation Rules

## Plugin method calls

Any exception raised inside a plugin method (`twin.step()`, `sensor.observe()`, `fault.apply()`, etc.) must be caught by the caller (always the simulation engine) and re-raised as `PluginExecutionError`:

```python
try:
    new_state = twin.step(state, dt)
except Exception as exc:
    raise PluginExecutionError(
        f"twin '{twin.twin_id}' raised an error in step()"
    ) from exc
```

`PluginExecutionError` is then handled by the engine's session error handler, which sets the session to `FAILED` and logs the full traceback. It is never propagated to the API layer.

## API layer

The API layer has a global exception handler that maps EPIC exceptions to HTTP responses:

```python
@app.exception_handler(EPICError)
async def epic_error_handler(request, exc):
    return JSONResponse(
        status_code=error_to_status_code(exc),
        content={"error": {"code": error_to_code(exc), "message": str(exc)}}
    )
```

Unhandled Python exceptions (i.e. bugs in the Core itself) return `500 Internal Server Error` with a generic message. Stack traces are never included in API responses.

---

# Exception to HTTP Status Code Mapping

| Exception | HTTP Status | Error Code |
|---|---|---|
| `PluginNotFoundError` | 404 | `PLUGIN_NOT_FOUND` |
| `SessionNotFoundError` | 404 | `SESSION_NOT_FOUND` |
| `ContestNotFoundError` | 404 | `CONTEST_NOT_FOUND` |
| `ContestStateError` | 409 | `CONTEST_STATE_ERROR` |
| `SessionStateError` | 409 | `SESSION_STATE_ERROR` |
| `RegistrationError` | 409 | `REGISTRATION_ERROR` |
| `SubmissionError` | 422 | `SUBMISSION_ERROR` |
| `EPICValidationError` | 422 | `VALIDATION_ERROR` |
| `InvalidCredentialsError` | 401 | `INVALID_CREDENTIALS` |
| `InsufficientPermissionsError` | 403 | `FORBIDDEN` |
| `PluginValidationError` | 500 | `PLUGIN_VALIDATION_ERROR` |
| `PluginExecutionError` | 500 | `PLUGIN_EXECUTION_ERROR` |
| Any other `EPICError` | 500 | `INTERNAL_ERROR` |

---

# API Error Response Format

All error responses follow the format defined in [API Specification](api-specification.md):

```json
{
  "error": {
    "code": "CONTEST_NOT_FOUND",
    "message": "Contest 'forecast_2027' does not exist"
  }
}
```

Error codes are uppercase snake-case strings. They are stable across versions — clients may depend on them for programmatic error handling.

---

# Logging

Every exception caught by the engine or the API layer must be logged with its full traceback at `ERROR` level.

`PluginExecutionError` must include the plugin id, the method that failed, and the original exception in the log entry.

In `DEBUG` mode, stack traces are additionally included in `500` API responses to assist development.

---

# Plugin Failure Isolation

A plugin failure must never affect other sessions.

Each simulation session runs as an independent `asyncio.Task`. An unhandled exception inside a task does not propagate to other tasks.

If a plugin raises an exception during session execution, the engine catches it, marks the session as `FAILED`, and cancels the task. All other running sessions continue unaffected.

---

# Startup Errors

If a plugin fails validation during registration at startup, `PluginValidationError` is raised immediately.

The application will refuse to start with a clear error message identifying the faulty plugin and the validation failure reason.

This is intentional: a mis-implemented plugin should be caught at startup, not during a live session.
