"""Document base + MIME→subclass mapping. Subclasses live in documents/."""
from __future__ import annotations

from . import _formats
from . import exceptions as exc
from .backend import Backend
from .comments import Comment, CommentCollection
from .permissions import PermissionsMixin

MIME_TO_TYPE = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
}


def occurrences_changed(resp: dict) -> int:
    """`occurrencesChanged` from a replaceAllText batchUpdate reply (0 if absent) —
    shared by Doc.replace_text and Slides.replace_text."""
    return (resp.get("replies") or [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)


class CommentsMixin:
    """Provides `comments` and `create_comment()` uniformly across document types.
    A subclass may define `_locate_comment(raw_dict)` to enrich `Comment.location` via the locate hook."""

    # Provided by the concrete Document subclass (declared here for the type checker).
    _backend: Backend
    id: str
    read_only: bool

    @property
    def comments(self) -> CommentCollection:
        return CommentCollection(self._backend, self.id, self.read_only,
                                 locate=getattr(self, "_locate_comment", None))

    def create_comment(self, content: str) -> Comment:
        if self.read_only:
            raise exc.ReadOnlyError("workspace is read_only; cannot create a comment")
        d = self._backend.create_comment(self.id, content)
        return self.comments._wrap(d)


class Document(CommentsMixin, PermissionsMixin):
    """Abstract base. Never instantiated directly — use Workspace.open().

    Uniform Drive concerns arrive as mixins, one per concern — `CommentsMixin`,
    `PermissionsMixin`, and later revisions/approvals. They are all the same shape: one
    Drive API, identical across Docs/Sheets/Slides. The per-type *content* axis is the
    subclasses in `documents/`.
    """

    def __init__(self, backend: Backend, metadata: dict, read_only: bool):
        self._backend = backend
        self.id = metadata["id"]
        self.name = metadata.get("name", "")
        self.mime_type = metadata["mimeType"]
        self.type = MIME_TO_TYPE[self.mime_type]
        self.url = metadata.get("webViewLink", "")
        self.read_only = read_only

    def reload(self) -> None:
        """Drop cached state. Subclasses (e.g. Sheet) override this to clear their own caches."""

    def export(self, mime_type: str) -> bytes:
        """Export this file's bytes. Accepts a mime type or a short alias ("markdown",
        "pdf", "docx"); rejects formats Drive will not produce for this type, rather than
        letting a bad one become a 400 from Google."""
        return self._backend.export_file(self.id, _formats.resolve(mime_type, self.type))

    @property
    def export_formats(self) -> tuple[str, ...]:
        """The mime types this document type can be exported as."""
        return _formats.EXPORT_FORMATS[self.type]

    def _require_writable(self) -> None:
        if self.read_only:
            raise exc.ReadOnlyError("workspace is read_only; content writes are disabled")

    # ── File lifecycle ────────────────────────────────────────────────────────────────
    #
    # Metadata only, which is what Drive calls an update and what Google's and Claude's MCP
    # servers mean by `update_file`. Changing a file's CONTENT is per-type and lives on the
    # subclasses (`replace_text`, `update`, `insert_text`).

    def rename(self, name: str) -> dict:
        """Change the file's name. Requires the `file.update` capability."""
        if not name or not name.strip():
            raise ValueError("a file name cannot be empty")
        self._require_writable()
        return self._backend.update_file_metadata(self.id, name=name)

    def move(self, parent_id: str, *, from_parent_id: str | None = None) -> dict:
        """Move the file into `parent_id`. Requires the `file.update` capability.

        Drive moves a file by editing its parent list rather than by taking a destination, so
        without `from_parent_id` this ADDS a parent and the file then lives in both places -
        which is a real Drive state, not a bug, and occasionally what you want. Pass the old
        parent to move rather than to add; a file's current parents are on its metadata.
        """
        self._require_writable()
        return self._backend.update_file_metadata(
            self.id, add_parent=parent_id, remove_parent=from_parent_id)

    def trash(self) -> dict:
        """Move the file to the trash. Requires the `file.trash` capability.

        Recoverable: Drive keeps a trashed file for 30 days and `untrash()` restores it.
        There is deliberately no permanent-delete anywhere in this library.
        """
        self._require_writable()
        return self._backend.trash_file(self.id, trashed=True)

    def untrash(self) -> dict:
        """Restore a trashed file. Requires the `file.trash` capability."""
        self._require_writable()
        return self._backend.trash_file(self.id, trashed=False)


def subclass_for_mime(mime: str) -> type[Document]:
    if mime not in MIME_TO_TYPE:
        raise exc.UnsupportedOperation(f"unsupported file type: {mime}")
    from .documents.doc import Doc
    from .documents.sheet import Sheet
    from .documents.slides import Slides
    return {"document": Doc, "spreadsheet": Sheet, "presentation": Slides}[MIME_TO_TYPE[mime]]
