"""Which capability each MCP tool can require — so the server stops advertising authority
its tool surface cannot exercise.

The bug this fixes, found by a model that read `describe_configuration`, planned work on the
strength of it, and only then discovered the tools did not exist: the `editor` profile enables
`content.write`, `file.create`, `comment.edit` and `comment.delete`, and **no tool in this
server uses any of them**. They are real policy — a library embedder going through
`Workspace.from_credentials` with that policy genuinely can call `doc.replace_text` — but
reporting them to a model as "enabled" reads as "available", and it is not.

`policy._GATES` answers "what does this *Backend method* cost?". This answers "what can this
*server* actually reach?". Both are needed, because the MCP layer deliberately exposes only
part of the library.

Lives beside `_resources.py` rather than inside `_tools/` because both need it: putting it in
the tools package made `_resources` -> `_tools._capabilities` -> `_tools/__init__` ->
`_tools.config` -> `_resources` a cycle. It is a statement *about* the server, not a tool.

Fail-closed like `_GATES`: `tests/test_mcp_capabilities.py` asserts every registered tool
appears here, so a new tool cannot arrive undeclared and silently widen what the server claims.
"""
from __future__ import annotations

from ..policy import (
    COMMENT_CREATE,
    COMMENT_DELETE,
    COMMENT_EDIT,
    COMMENT_REPLY,
    COMMENT_RESOLVE,
    CONTENT_WRITE,
    FILE_CREATE,
    FILE_SHARE,
    FILE_TRASH,
    FILE_UPDATE,
)

# Tool name -> the capability a call to it can require, or None for a read.
#
# One entry per registered tool. A read is `None` rather than absent, so a missing key means
# "nobody decided" rather than "it is a read".
TOOL_CAPABILITIES: dict[str, str | None] = {
    # discovery and reads
    "search_files": None,
    "list_recent_files": None,
    "get_file_metadata": None,
    "get_file_permissions": None,
    "read_file_content": None,
    "download_file_content": None,
    "list_comments": None,
    "get_comment": None,
    "comments_by_cell": None,
    # A read, and it stays a read: accept/reject would need a capability, and the Docs API
    # has no endpoint for either, so there is nothing to gate.
    "list_suggestions": None,
    # comment writes
    "create_comment": COMMENT_CREATE,
    "reply_comment": COMMENT_REPLY,
    "resolve_comment": COMMENT_RESOLVE,
    "reopen_comment": COMMENT_RESOLVE,
    "edit_comment": COMMENT_EDIT,
    "delete_comment": COMMENT_DELETE,
    # content writes
    "replace_text": CONTENT_WRITE,
    "append_text": CONTENT_WRITE,
    "update_cells": CONTENT_WRITE,
    "append_rows": CONTENT_WRITE,
    "list_slides": None,
    "insert_slide_text": CONTENT_WRITE,
    # creation
    "create_file": FILE_CREATE,
    "copy_file": FILE_CREATE,
    # file lifecycle - each maps to the capability that gates it, so
    # `capabilities_unreachable` becomes empty for the `full` profile: every capability the
    # policy can grant now has a tool that uses it.
    "update_file": FILE_UPDATE,
    "trash_file": FILE_TRASH,
    "share_file": FILE_SHARE,
    # about the server rather than about Google; no Google call, so no capability
    "describe_configuration": None,
    # A read in the strict sense - it touches no Google API at all, only this process.
    "report_a_problem": None,
    # Returns a plan; carrying it out is the model calling the tools it names,
    # each of which is gated on its own.
    "demonstration_plan": None,
    "read_server_resource": None,
    "authenticate": None,
}


def reachable_capabilities() -> frozenset[str]:
    """Capabilities some tool in this server can actually require."""
    return frozenset(c for c in TOOL_CAPABILITIES.values() if c is not None)
