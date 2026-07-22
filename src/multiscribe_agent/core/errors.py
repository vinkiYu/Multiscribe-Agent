"""Domain exception hierarchy for MultiscribeAgent."""


class MultiscribeError(Exception):
    """Base class for all application-level errors."""


class ConfigError(MultiscribeError):
    """Raised when application configuration is invalid or unavailable."""


class ValidationError(MultiscribeError):
    """Raised when a domain value violates an application invariant."""


class ProviderError(MultiscribeError):
    """Raised when an AI provider request or response fails."""


class ToolExecutionError(MultiscribeError):
    """Raised when an agent tool cannot complete its operation."""


class ToolApprovalRequired(ToolExecutionError):
    """Raised when a high-risk tool call has no matching operator approval."""


class WorkflowError(MultiscribeError):
    """Raised when workflow validation or execution fails."""


class PublisherError(MultiscribeError):
    """Raised when publishing content to an external destination fails."""


class AdapterError(MultiscribeError):
    """Raised when a content adapter cannot fetch or transform data."""


class AuthError(MultiscribeError):
    """Raised when authentication or authorization fails."""
