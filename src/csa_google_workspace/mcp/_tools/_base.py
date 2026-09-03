"""Shared machinery for the tool modules: error translation, capability probing, annotations.

Lifted verbatim out of `server.py` when the tool surface outgrew one file. The comments
here record *why* each piece exists; they are the expensive part.
"""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ... import exceptions as exc
from ...workspace import Workspace
from .. import _untrusted

log = logging.getLogger(__name__)

WorkspaceProviderT = Callable[[], Workspace]

# `open_world_hint=True` on every one of them (#326), which is the annotation that says the
# result comes from OUTSIDE this server and should be scrutinised. On a server whose entire
# surface returns third-party content it is not a nuance: document text, comment bodies, file
# names, tab titles and an access requester's own display name are all written by somebody else,
# and prompt injection through them is the primary risk this project names for itself.
#
# It is on the WRITES too, deliberately. A write returns Google's response - ids, names, a
# permission - so the reply is third-party content even when the request was not, and a
# distinction that has to be re-derived per tool is one that drifts.
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                       open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                        open_world_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False,
                              open_world_hint=True)


def _errors(fn):
    """Translate the library's typed exceptions into readable tool errors, and record the call.

    Must raise the SDK's `ToolError`, not a plain exception: anything else becomes an
    `UnexpectedToolError` whose message the SDK deliberately suppresses, so the user would
    see "Error executing tool read_file_content" and nothing about what actually went wrong.

    Startup-ish failures (no credentials) arrive here too, because the workspace resolves
    on first use — so the user reads the remedy in chat instead of seeing a dead connector.

    **Every tool passes through here**, which makes it the one place a call can be recorded
    without touching thirty-six handlers. What is recorded is deliberately thin: the **tool
    name**, the **file id**, the outcome, and the duration.

    **Every result also passes through `_untrusted.scrub`**, for the same reason: it is the one
    place that catches every tool, including one added later. That removes terminal control
    sequences from returned strings, which JSON escaping does not - see `mcp/_untrusted.py` for
    the probe and for why `\r` is deliberately left alone.

    **Never the other arguments.** `create_comment` carries comment text, `replace_text` carries
    a replacement, `update_cells` carries a grid — all document content. Our stderr is persisted
    by the MCP client into a cache directory we cannot see or purge, so logging arguments "for
    debugging" is how untrusted content becomes a durable artifact outside its own governance.
    See `mcp/_logging.py`.
    """
    @functools.wraps(fn)          # keeps __wrapped__ so the SDK can read the real signature
    def wrapped(*args, **kwargs):
        started = time.monotonic()
        file_id = kwargs.get("fileId") or kwargs.get("file_id")
        log.debug("%s called%s", fn.__name__, f" on {file_id}" if file_id else "")
        try:
            result = fn(*args, **kwargs)
        except exc.ReadOnlyError as e:
            raise _refused(fn, started, e, ToolError(f"server is read-only: {e}")) from e
        except exc.NotFoundError as e:
            raise _refused(fn, started, e, ToolError(f"not found: {e}")) from e
        except exc.AccessError as e:
            raise _refused(fn, started, e, ToolError(f"permission denied: {e}")) from e
        except exc.AuthError as e:
            raise _refused(fn, started, e, ToolError(str(e))) from e
        except exc.ConflictError as e:
            # Added by #313, which found it as a LEAK and it was also broken: outside the
            # ladder it became an `UnexpectedToolError` whose message the SDK drops, so a
            # caller who asked for a tab name that already exists saw "Error executing tool
            # add_tab" and never learned the name had clashed. Both halves fixed by one line.
            raise _refused(fn, started, e, ToolError(f"conflict: {e}")) from e
        except exc.UnsupportedOperation as e:
            raise _refused(fn, started, e, ToolError(str(e))) from e
        except exc.ApiError as e:
            # A Google 4xx that is not one of the typed cases above - most often a malformed
            # Drive query, which `search_files` accepts as a raw `q` string. Without this it
            # became an UnexpectedToolError with the message suppressed, so the model saw
            # "Error executing tool search_files" and had nothing to correct. Found by the
            # demonstration, which passed free text where Drive syntax was required.
            raise _refused(fn, started, e,
                           ToolError(f"Google rejected the request: {e}")) from e
        except ValueError as e:
            # The library raises plain ValueError for a bad argument value (an unknown
            # `order_by`, an empty query, `as_text(suggestions="maybe")`). Without this
            # clause every one of those became an UnexpectedToolError with the message
            # dropped — so the model saw "Error executing tool X" and could not correct
            # itself. Found by a test on list_recent_files; it was never search-specific.
            raise _refused(fn, started, e, ToolError(f"invalid argument: {e}")) from e
        except Exception as e:
            # Not translated — re-raised as-is, so the SDK's own handling applies. Recorded at
            # ERROR because everything above is the system working and this is not.
            # Type only, like `_refused` and for the same reason (#313): this is the record
            # that IS emitted at the default level, so it is the one that reaches the client's
            # cache. An untranslated exception is a bug in the ladder below, and knowing WHICH
            # exception is what a reader needs - the message adds content, not diagnosis.
            log.error("%s failed after %s: %s", fn.__name__, _took(started), type(e).__name__)
            raise
        log.info("%s ok in %s%s", fn.__name__, _took(started),
                 f" ({file_id})" if file_id else "")
        return _untrusted.scrub(result)
    return wrapped


def _took(started: float) -> str:
    return f"{(time.monotonic() - started) * 1000:.0f}ms"


def _refused(fn, started, cause, translated):
    """Record an expected refusal and hand back the `ToolError` to raise.

    INFO rather than WARNING: a policy refusal, a missing file or a bad argument is the system
    working as designed. Logging them as warnings would make a correctly-configured server look
    unhealthy, and a log that cries wolf gets filtered out — taking the real warnings with it.

    **The MESSAGE is deliberately not logged** (#313), and the reasoning this replaces was
    wrong in an instructive way. It said: *"the message is the one the caller already receives,
    so this adds no exposure."* Same text, but **different destinations with different
    governance** — the caller's copy goes to the model for one turn, while the log goes to a
    cache directory this server cannot rotate, purge or even read, under the client's retention.

    And these messages carry document content. `sheet.py` refuses a missing tab with
    *"present: ['Q3 Layoff Plan', 'Comp Bands']"* — genuinely useful to the caller, and tab
    titles are content, so logging them defeats the rule `_logging.py` states for itself:
    raising the verbosity raises detail about the OPERATION, never about the CONTENT.

    So the caller keeps the full message and the log gets the exception type. Fixed HERE rather
    than by shortening each message, for the same reason `_untrusted.scrub` runs at the
    boundary: a per-message rule is a list somebody maintains, and the next message that
    carries a title will not be on it.
    """
    log.info("%s refused after %s: %s", fn.__name__, _took(started), type(cause).__name__)
    return translated


def _require(doc: Any, attr: str, what: str):
    """The factory-dispatch alternative to a type ladder: ask the object, not its label."""
    method = getattr(doc, attr, None)
    if method is None:
        raise exc.UnsupportedOperation(
            f"{what} is not supported for {doc.type}s (this file is a {doc.type})")
    return method
