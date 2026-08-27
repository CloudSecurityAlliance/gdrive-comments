"""Structured-output shapes for tool results.

Plain dicts built by hand rather than re-exporting the domain models, for two reasons:
the models carry deliberately redacting `__repr__`s and mutation methods that mean nothing
over the wire, and the wire shape is a contract we control independently of the library's
internals. `author` is the display name only — email is usually absent from the API and is
not surfaced (SECURITY.md). Comment *content* is returned: the agent needs it, and the
redacted repr protects logs, not tool output.
"""
from __future__ import annotations

import re
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
    cell: str | None          # where DRIVE anchored it: A1 for anything created via the API
    linked_cell: str | None   # the cell its deep link points at, if it has one
    # The passage the comment is attached to, from Drive's `quotedFileContent`. `None` means
    # the comment is on the FILE rather than on a passage - a real and common state ("looks
    # good to me") - which is why it is not an empty string.
    #
    # It was modelled in the library and NOT exposed here, which is how a comment register
    # ended up missing the column somebody actually wants: a model could list twenty comments
    # on a draft and not say which paragraph any of them referred to. It stayed hidden because
    # `_inline.py` consumes it for read_file_content(includeComments), so the field looked used.
    quoted_text: str | None
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
    # `grantee_type`, not `type`. Everywhere else in this surface `type` is the DOCUMENT kind
    # - document / spreadsheet / presentation - and a model reads these outputs interleaved.
    # One field name carrying two unrelated vocabularies is a misreading waiting to happen,
    # and renaming it costs nothing before 1.0.0 and is impossible after.
    grantee_type: str         # user | group | domain | anyone
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
    server_version: str                # csa-google-workspace's own version
    # The environment, carried here and not only in `report_a_problem`, because this is the
    # tool a model calls after any refusal — so the facts a bug report needs end up in the
    # transcript as a side effect of ordinary use, rather than only when somebody thinks to
    # ask for a report. A conversation pasted into an issue then arrives complete.
    os: str                            # named as a person would: "macOS 26.6.2", "Windows 11"
    architecture: str
    python_version: str
    installed_via: str                 # pipx | pip (venv) | pip (shared environment) | source
    help_resource: str                 # the resource URI, for clients that surface resources
    help_tool: str                     # ...and the tool, for clients that do not


class SlideOut(TypedDict):
    index: int                        # 1-based, as a person counts slides
    shape_ids: list[str]              # text-capable shapes, for insert_slide_text
    text: str
    notes: str


class SlidesOut(TypedDict):
    slides: list[SlideOut]


class EditOut(TypedDict):
    file_id: str
    type: str
    occurrences_changed: int | None   # None where the operation has no natural count
    detail: str


class ResourceOut(TypedDict):
    uri: str
    content: str


class CommentsOut(TypedDict):
    comments: list[CommentOut]


class CommentExportOut(TypedDict):
    """A bulk comment register: flat rows, ordered columns, and what not to trust.

    `columns` is ordered so writing a spreadsheet is a loop. `rows` is one row per comment AND
    per reply with `reply_to` naming the thread - the lossless shape, since one-row-per-thread
    is a group-by away and the reverse is not. `caveats` is where the multi-tab ambiguity is
    stated rather than papered over.
    """
    columns: list[str]
    rows: list[dict]
    caveats: list[str]
    thread_count: int
    row_count: int
    file_id: str
    file_name: str
    file_type: str
    destination: str            # rows | csv | sheet | file
    csv: str | None             # destination="csv": the text, RFC 4180
    sheet_id: str | None        # destination="sheet"
    sheet_url: str | None       # destination="sheet": hand this to the user
    written_path: str | None    # destination="file"
    detail: str


class ActionRowOut(TypedDict):
    thread_id: str
    replied: bool
    resolved: bool
    reopened: bool
    deleted: bool
    failed: bool
    detail: str


class ApplyActionsOut(TypedDict):
    """What a filled-in register did, or would do.

    `applied` false means nothing happened - that is the default, because the blast radius is
    somebody's review under their own name. `would_reply` / `would_resolve` are the dry run's
    answer; `replied` / `resolved` are the real one.
    """
    applied: bool
    replied: int
    resolved: int
    reopened: int
    deleted: int
    would_reply: int
    would_resolve: int
    would_reopen: int
    would_delete: int
    skipped: int
    failed: int
    rows: list[ActionRowOut]
    file_id: str
    file_name: str
    source: str
    detail: str


class CellCommentsOut(TypedDict):
    """`comments_by_cell` - the answer, plus how much to trust it. (D3)

    The XLSX export carries one `threadedComments` member per SHEET, and the parse collects
    them flat with no record of which sheet each came from. So on a multi-tab workbook a
    comment at B11 on Sheet3 is indistinguishable from one at B11 on Sheet1. The ambiguity is
    reported rather than resolved, because a silently-wrong cell is worse than a stated
    uncertainty - and it is reported ONLY when there is more than one tab, since on a
    single-tab workbook the answer is exact and a warning would be noise.
    """
    comments: list[CommentOut]
    tab_ambiguous: bool
    tabs: list[str]
    detail: str


class TextOut(TypedDict):
    text: str


class SuggestionOut(TypedDict):
    suggestion_id: str
    kind: str                         # insertion | deletion
    text: str
    # No `author`. The Docs API does not expose one, and a permanently-null field is an
    # invitation to attribute somebody's edit to nobody.


class SuggestionsOut(TypedDict):
    suggestions: list[SuggestionOut]
    # Carried in the RESULT, not only the tool description. A model reads a description once,
    # when choosing the tool, and then reads the result - so by the time it is composing
    # "shall I accept these?" the description is thousands of tokens behind it and this is
    # what is in front of it.
    can_accept_or_reject: bool
    detail: str


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


# `...range=B2` at the end of a deep link this library appended. Read back out rather than
# remembered, so a comment fetched in a later session reports the same thing as one just made.
_LINKED_CELL = re.compile(r"[?&#]range=([A-Z]+[0-9]+)\b")


def comment_out(comment: Any) -> CommentOut:
    location = getattr(comment, "location", None)
    linked = _LINKED_CELL.search(comment.content or "")
    return {
        "id": comment.id,
        "author": getattr(comment.author, "display_name", None) if comment.author else None,
        "content": comment.content,
        "resolved": bool(comment.resolved),
        "created_time": _iso(comment.created_time),
        # Two different facts, and conflating them under one name misled an end-to-end run
        # into reporting the wrong cell to a user. `cell` is where DRIVE anchored the comment
        # -- which for anything created through the API is A1, always, because the API cannot
        # anchor a comment to a cell at all. `linked_cell` is the cell the deep link points
        # at, which is what somebody asked for.
        "cell": getattr(location, "cell", None) if location else None,
        "linked_cell": linked.group(1) if linked else None,
        "quoted_text": getattr(comment, "quoted_text", None),
        "replies": [reply_out(r) for r in (comment.replies or [])],
    }


_NO_ACCEPT = (
    "Read-only: the Google Docs API has no accept or reject endpoint, so no tool here can "
    "apply or discard a suggestion. It has to be done in the document. Use "
    "read_file_content(suggestions=\"accepted\"|\"rejected\") to see what the document would "
    "say either way.")


def suggestions_out(found: list) -> SuggestionsOut:
    return {
        "suggestions": [{"suggestion_id": s.suggestion_id, "kind": s.kind, "text": s.text}
                        for s in found],
        "can_accept_or_reject": False,
        # Said even when the list is empty, because "nothing suggested" and "I could not
        # tell" are different answers and a bare `[]` does not distinguish them.
        "detail": (f"{len(found)} suggestion(s). " if found else "No suggestions. ") + _NO_ACCEPT,
    }


def document_out(doc: Any) -> DocumentOut:
    return {"id": doc.id, "name": doc.name, "type": doc.type, "url": doc.url}


SNIPPET_CHARS = 500


def permission_out(p: Any) -> PermissionOut:
    return {"id": p.id, "grantee_type": p.type, "role": p.role,
            "display_name": p.display_name,
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


class ProblemReportOut(TypedDict):
    """What to put in a bug report, and where to put it.

    Carries no file ids, no titles and no paths: this is written to be pasted into a PUBLIC
    issue tracker. Scopes are described by shape ("every file", "3 files") rather than by
    content, which is the opposite of `ConfigOut` and deliberate — see `_environment`.
    """
    report: str                 # ready to paste, markdown
    issues_url: str
    new_issue_url: str          # prefilled, and already carries `label`
    label: str                  # the tracker label this will be filed under
    server_version: str
    python_version: str
    os: str
    architecture: str
    mcp_sdk_version: str | None
    installed_via: str
    profile: str | None
    read_only: bool
    read_scope: str
    modify_scope: str
    authorized: bool
    checklist: list[str]


class FileUpdateOut(TypedDict):
    """The result of a metadata change: what the file is now, not what it was."""
    id: str
    name: str | None
    # `None` means the response did not carry parents, NOT that the file has none - a file
    # with no parents is not a state Drive has. Hard-coded to `[]` until v0.21.0.
    parents: list[str] | None


class TrashOut(TypedDict):
    id: str
    name: str | None
    trashed: bool             # false after untrash, so one shape serves both directions


class DemonstrationStepOut(TypedDict):
    step: int
    tool: str
    do: str                    # what happens, in a sentence
    why: str | None            # worth saying out loud while doing it
    available: bool            # false when the current policy will refuse it
    applies_to: str            # document | spreadsheet | presentation | account | cleanup


class DemonstrationOut(TypedDict):
    """A plan to carry out, not a result. See `_tools/demo.py` for why it does not just run."""
    steps: list[DemonstrationStepOut]
    unavailable: list[str]     # what this policy refuses, said once per reason
    cleanup_possible: bool     # false -> the user deletes the files by hand; say so FIRST
    creates_real_files: bool
    unattended_command: str
    narrated_command: str
    advice: str

