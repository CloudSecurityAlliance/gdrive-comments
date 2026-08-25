"""Structured-output shapes for tool results.

Plain dicts built by hand rather than re-exporting the domain models, for two reasons:
the models carry deliberately redacting `__repr__`s and mutation methods that mean nothing
over the wire, and the wire shape is a contract we control independently of the library's
internals. `author` is the display name only — email is usually absent from the API and is
not surfaced (SECURITY.md). Comment *content* is returned: the agent needs it, and the
redacted repr protects logs, not tool output.
"""
from __future__ import annotations

from typing import Any, TypedDict


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


class CommentsOut(TypedDict):
    comments: list[CommentOut]


class TextOut(TypedDict):
    text: str


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
