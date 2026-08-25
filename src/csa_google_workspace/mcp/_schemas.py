"""Structured-output shapes for tool results.

Plain dicts built by hand rather than re-exporting the domain models, for two reasons:
the models carry deliberately redacting `__repr__`s and mutation methods that mean nothing
over the wire, and the wire shape is a contract we control independently of the library's
internals. `author` is the display name only — email is usually absent from the API and is
not surfaced (SECURITY.md). Comment *content* is returned: the agent needs it, and the
redacted repr protects logs, not tool output.
"""
from __future__ import annotations

import sys
from typing import Any

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    # Pydantic cannot introspect `typing.TypedDict` on Python < 3.12 (the runtime does not
    # expose __required_keys__ the way it needs), and fails *silently*: the tool still runs,
    # but structuredContent comes back null. Caught only by the CI matrix — a 3.12 dev box
    # passes. typing_extensions arrives with pydantic, which arrives with mcp.
    from typing_extensions import TypedDict


class ReplyOut(TypedDict):
    id: str
    author: str | None
    content: str | None
    created_time: str | None


class CommentOut(TypedDict):
    id: str
    author: str | None
    content: str | None
    resolved: bool
    created_time: str | None
    cell: str | None
    replies: list[ReplyOut]


class DocumentOut(TypedDict):
    id: str
    name: str
    type: str
    url: str


class FileMetadataOut(TypedDict):
    id: str
    name: str
    type: str
    mime_type: str
    url: str
    snippet: str | None       # leading text, unless excludeContentSnippets


class DownloadOut(TypedDict):
    content_base64: str
    mime_type: str
    size_bytes: int


class FileRefOut(TypedDict):
    id: str
    name: str
    type: str | None          # None for a type this library cannot open (PDF, folder, Form)
    mime_type: str
    url: str
    modified_time: str | None


class FilesOut(TypedDict):
    files: list[FileRefOut]


class PermissionOut(TypedDict):
    id: str
    type: str                 # user | group | domain | anyone
    role: str                 # reader | commenter | writer | fileOrganizer | organizer | owner
    display_name: str | None
    email: str | None         # the payload of this call, unlike elsewhere here
    domain: str | None
    can_write: bool
    is_public: bool


class PermissionsOut(TypedDict):
    permissions: list[PermissionOut]
    public: bool              # anyone-with-the-link; the thing worth noticing
    writers: int


class ConfigOut(TypedDict):
    """What this server may do. Reasons from the allowlist are deliberately absent — they are
    written for whoever reviews the configuration and may name people or unannounced work."""
    read_scope: str                    # "every file" | "no files" | "N listed file(s)"
    read_unrestricted: bool            # true when the scope is `*` — see readable_file_ids
    readable_file_ids: list[str]       # the listed ids; EMPTY when unrestricted, not "none"
    modify_scope: str
    modify_unrestricted: bool
    modifiable_file_ids: list[str]
    profile: str | None                # the CSA_GW_PROFILE name, if one is set
    capabilities_enabled: list[str]    # permitted by policy — includes the library's surface
    capabilities_reachable: list[str]  # ...and actually usable through a tool in THIS server
    capabilities_unreachable: list[str]  # enabled but no tool here uses them
    capabilities_disabled: list[str]
    read_only: bool
    blocked_reason: str | None         # why something permits nothing, when it does
    help_resource: str                 # where the full reference lives


class CommentsOut(TypedDict):
    comments: list[CommentOut]


class TextOut(TypedDict):
    text: str


class AuthOut(TypedDict):
    status: str          # authorized | already_authorized | declined | timed_out
    detail: str


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def reply_out(reply: Any) -> ReplyOut:
    return {
        "id": reply.id,
        "author": getattr(reply.author, "display_name", None) if reply.author else None,
        "content": reply.content,
        "created_time": _iso(reply.created_time),
    }


def comment_out(comment: Any) -> CommentOut:
    location = getattr(comment, "location", None)
    return {
        "id": comment.id,
        "author": getattr(comment.author, "display_name", None) if comment.author else None,
        "content": comment.content,
        "resolved": bool(comment.resolved),
        "created_time": _iso(comment.created_time),
        "cell": getattr(location, "cell", None) if location else None,
        "replies": [reply_out(r) for r in (comment.replies or [])],
    }


def document_out(doc: Any) -> DocumentOut:
    return {"id": doc.id, "name": doc.name, "type": doc.type, "url": doc.url}


SNIPPET_CHARS = 500


def permission_out(p: Any) -> PermissionOut:
    return {"id": p.id, "type": p.type, "role": p.role, "display_name": p.display_name,
            "email": p.email, "domain": p.domain, "can_write": p.can_write,
            "is_public": p.is_public}


def permissions_out(perms: list) -> PermissionsOut:
    """Rolls up the two facts a reviewer actually asks for, so the model does not have to
    derive them from the list and get it wrong."""
    return {"permissions": [permission_out(p) for p in perms],
            "public": any(p.is_public for p in perms),
            "writers": sum(1 for p in perms if p.can_write)}


def file_ref_out(ref: Any) -> FileRefOut:
    return {"id": ref.id, "name": ref.name, "type": ref.type, "mime_type": ref.mime_type,
            "url": ref.url, "modified_time": _iso(ref.modified_time)}


def file_metadata_out(doc: Any, snippet: str | None) -> FileMetadataOut:
    return {"id": doc.id, "name": doc.name, "type": doc.type, "mime_type": doc.mime_type,
            "url": doc.url, "snippet": snippet}
