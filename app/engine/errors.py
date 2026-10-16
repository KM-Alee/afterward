"""Deterministic engine failures. Codes are rule names, not user content."""


class EngineError(Exception):
    """A rule refused the operation. `code` is safe to log and return."""

    status_code = 400
    code = "engine_error"

    def __init__(self, code: str | None = None):
        self.code = code or type(self).code
        super().__init__(self.code)


class StalePlan(EngineError):
    """The plan id, version and hash the caller named are no longer current."""

    status_code = 409
    code = "stale"


class AlreadyDecided(EngineError):
    """A second actor arrived after this plan version was already approved."""

    status_code = 409
    code = "already_decided"


class DependencyRequired(EngineError):
    """Close and transfer stay blocked until a person has answered the dependency check."""

    status_code = 422
    code = "dependency_required"


class BlindRetryForbidden(EngineError):
    """An uncertain send is not sent again unless a search proved it never left."""

    status_code = 409
    code = "blind_retry"


class CrisisPaused(EngineError):
    """Crisis language pauses admin. The care text is a template, not a model reply."""

    status_code = 409
    code = "crisis"


class AIUnavailable(EngineError):
    """The model call did not return a usable proposal. Nothing is sent on a guess."""

    status_code = 503
    code = "ai_unavailable"
