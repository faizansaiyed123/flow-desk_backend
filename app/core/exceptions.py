"""Domain-level exceptions.

Services raise these instead of HTTPException so business logic stays
transport-agnostic (testable without spinning up FastAPI). A single
exception handler in main.py translates each into the right HTTP response.
"""


class FlowDeskError(Exception):
    """Base class for all domain errors."""

    status_code = 400
    default_message = "An error occurred."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(FlowDeskError):
    status_code = 404
    default_message = "Resource not found."


class ValidationError(FlowDeskError):
    status_code = 422
    default_message = "Invalid data."


class ConflictError(FlowDeskError):
    status_code = 409
    default_message = "This action conflicts with existing data."


class AuthenticationError(FlowDeskError):
    status_code = 401
    default_message = "Authentication failed."


class AuthorizationError(FlowDeskError):
    status_code = 403
    default_message = "You do not have permission to perform this action."


class RateLimitError(FlowDeskError):
    status_code = 429
    default_message = "Too many requests."
