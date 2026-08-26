"""Shared machinery for the tool modules: error translation, capability probing, annotations.

Lifted verbatim out of `server.py` when the tool surface outgrew one file. The comments
here record *why* each piece exists; they are the expensive part.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ... import exceptions as exc
from ...workspace import Workspace

WorkspaceProviderT = Callable[[], Workspace]

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False)


def _errors(fn):
    """Translate the library's typed exceptions into readable tool errors.

    Must raise the SDK's `ToolError`, not a plain exception: anything else becomes an
    `UnexpectedToolError` whose message the SDK deliberately suppresses, so the user would
    see "Error executing tool read_file_content" and nothing about what actually went wrong.

    Startup-ish failures (no credentials) arrive here too, because the workspace resolves
    on first use — so the user reads the remedy in chat instead of seeing a dead connector.
    """
    @functools.wraps(fn)          # keeps __wrapped__ so the SDK can read the real signature
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except exc.ReadOnlyError as e:
            raise ToolError(f"server is read-only: {e}") from e
        except exc.NotFoundError as e:
            raise ToolError(f"not found: {e}") from e
        except exc.AccessError as e:
            raise ToolError(f"permission denied: {e}") from e
        except exc.AuthError as e:
            raise ToolError(str(e)) from e
        except exc.UnsupportedOperation as e:
            raise ToolError(str(e)) from e
        except exc.ApiError as e:
            # A Google 4xx that is not one of the typed cases above - most often a malformed
            # Drive query, which `search_files` accepts as a raw `q` string. Without this it
            # became an UnexpectedToolError with the message suppressed, so the model saw
            # "Error executing tool search_files" and had nothing to correct. Found by the
            # demonstration, which passed free text where Drive syntax was required.
            raise ToolError(f"Google rejected the request: {e}") from e
        except ValueError as e:
            # The library raises plain ValueError for a bad argument value (an unknown
            # `order_by`, an empty query, `as_text(suggestions="maybe")`). Without this
            # clause every one of those became an UnexpectedToolError with the message
            # dropped — so the model saw "Error executing tool X" and could not correct
            # itself. Found by a test on list_recent_files; it was never search-specific.
            raise ToolError(f"invalid argument: {e}") from e
    return wrapped


def _require(doc: Any, attr: str, what: str):
    """The factory-dispatch alternative to a type ladder: ask the object, not its label."""
    method = getattr(doc, attr, None)
    if method is None:
        raise exc.UnsupportedOperation(
            f"{what} is not supported for {doc.type}s (this file is a {doc.type})")
    return method
