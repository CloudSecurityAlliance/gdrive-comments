"""Typed error hierarchy. Callers never touch raw googleapiclient HttpError."""


class CsaWorkspaceError(Exception):
    """Base for every library error."""


class AuthError(CsaWorkspaceError):
    """Bad/expired credentials, or consent needed."""


class ServiceDisabledError(CsaWorkspaceError):
    """A Google API is not enabled in the Cloud project (403 SERVICE_DISABLED)."""

    def __init__(self, service: str, activation_url: str):
        self.service = service
        self.activation_url = activation_url
        super().__init__(
            f"The API '{service}' is not enabled for this Google Cloud project. "
            f"Enable it at {activation_url} and retry (allow a few minutes to propagate)."
        )


class ReadOnlyError(CsaWorkspaceError):
    """A mutating call was made while the workspace is read_only=True."""


class NotFoundError(CsaWorkspaceError):
    """A file, comment, or reply id does not exist (404)."""


class ConflictError(CsaWorkspaceError):
    """The request is well-formed but the current state refuses it.

    Its own type so a caller can tell "already there" from "went wrong", which matters most for
    the operation that motivated it: adding a spreadsheet tab whose name is taken. Google would
    quietly create `Title 2`; a caller re-running a register build needs the difference between
    *created* and *already present*, and a generic error makes both look like failure.

    Also raised for deleting the only tab in a file, which Google refuses too.
    """


class InvalidInputError(CsaWorkspaceError):
    """The request was refused because of WHAT WAS SENT, not because of who sent it.

    Its own type because **Google returns 403 for this**, and a 403 otherwise means *permission*.
    Measured 2026-09-05: posting a comment body over the limit returns
    ``403 commentLengthLimitExceeded``, *"Comment content is limited to 4096 bytes in UTF-8
    encoding."* Without this type that arrives as `AccessError`, and an embedder that catches
    `AccessError` does the wrong thing twice over — it tells the user they lack access to a file
    they can plainly edit, and it may re-run the OAuth flow to fix a problem no credential can
    fix. The remedy is to send less text.

    The 4096 bytes are **UTF-8 bytes, not characters**, so a comment of emoji or CJK text hits
    the limit at roughly a quarter of the length an ASCII one does. Google's own message is
    preserved verbatim in `str(e)`, because it states the current limit and this docstring only
    states the limit as measured on one day.
    """


class AccessError(CsaWorkspaceError):
    """Insufficient permission (403) — not shared, wrong scope, or editing another's comment."""


class RateLimitError(CsaWorkspaceError):
    """Rate limit hit (429). `retry_after` is seconds, if the server provided it."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited; retry after {retry_after}s" if retry_after else "Rate limited")


class UnsupportedOperation(CsaWorkspaceError):
    """The operation cannot be performed — and the message MUST say **whose limit it is**.

    **The governing principle (CINO, 2026-09-03): capability is never the constraint, policy
    is.** *"The MCP server cannot do that"* must never be a technical answer. The answer should
    always be shaped like *"that is risky, so it is gated off and disabled by default — and if
    you want it on, it can be on."* Whether to let an AI do something is a **business and risk
    decision**, and a missing implementation quietly makes that decision on somebody's behalf.

    Which means there are exactly **two** legitimate reasons to raise this, and a message that
    does not say which one it is has answered the wrong question:

    * **UPSTREAM** — Google will not do it, or not yet. Legitimate, and it must cite the
      MEASUREMENT and say what would unlock it (enrolment, a scope, a GA date). This is the
      shape that stops a false *"impossible"* outliving the fact: the accept/reject-suggestion
      message claimed a `PlaywrightBackend` was *required* for months after
      `acceptSuggestion` was measured to exist in Developer Preview.
    * **NOT ENABLED** — the operator has switched it off. Recoverable by configuration, and the
      message must say which setting, so the reply can be *"we gated that"* rather than
      *"that is unsupported"*.

    A third use is a **bug** rather than a refusal — an undeclared gate, a file-scoped method
    called without a file id — and those say "This is a bug" in the message on purpose.

    `tests/test_refusals_name_their_kind.py` asserts the property, because a message is the
    only place this distinction lives and prose rots.
    """


class DetachedError(CsaWorkspaceError):
    """A Comment/Reply built via `from_api()` (not obtained through a Workspace) has no
    backend attached and cannot be mutated. Fetch it via `Workspace.open(...).comments`."""


class ApiError(CsaWorkspaceError):
    """Catch-all wrapper for an unclassified googleapiclient HttpError."""

    def __init__(self, status: int, reason: str, message: str):
        self.status = status
        self.reason = reason
        super().__init__(f"[{status} {reason}] {message}")
