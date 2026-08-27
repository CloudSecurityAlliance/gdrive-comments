"""The account axis: finding files, rather than operating on one you already named.

Everything else in this library hangs off `Workspace.open(file_id)`. Search cannot: you
cannot open a file you are trying to find. So this is the second axis the structure review
called for (docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md) —
reached as `workspace.files`, a *collection*, following `CommentCollection`'s precedent
rather than bolting methods onto the entry point.

A result is a `FileRef`, not a `Document`: search returns metadata for files of any type,
including ones this library cannot open, and materialising a `Document` per hit would mean
a fetch per hit. `FileRef.open()` is the upgrade when you actually want one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import exceptions as exc
from .backend import Backend
from .base import MIME_TO_TYPE

if TYPE_CHECKING:                                     # pragma: no cover
    from .base import Document
    from .permissions import Permission

# What the connector and Google's server both accept, mapped to Drive `orderBy` values.
ORDER_BY = {
    "recency": "recency desc",
    "lastModified": "modifiedTime desc",
    "lastModifiedByMe": "modifiedByMeTime desc",
}

MAX_PAGE_SIZE = 100

# What `create()` accepts, and the Google mime type each maps to. A folder is a file in Drive,
# which is why it belongs in the same call rather than a separate one.
KINDS = {
    "document": "application/vnd.google-apps.document",
    "spreadsheet": "application/vnd.google-apps.spreadsheet",
    "presentation": "application/vnd.google-apps.presentation",
    "folder": "application/vnd.google-apps.folder",
}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:                                 # Drive sent something unexpected
        return None


@dataclass(repr=False)
class FileRef:
    """A search hit: enough to decide whether to open it, and no more.

    `type` is `None` for anything this library cannot open (a PDF, a folder, a Form).
    Search legitimately returns those; pretending otherwise would hide results.
    """
    id: str
    name: str
    mime_type: str
    url: str
    modified_time: datetime | None = None
    # `None` means NOT ASKED FOR; `()` means genuinely no parents. The distinction is the
    # whole value of the field: `search` does not request parents, so a search hit that
    # reported `()` would be asserting a fact it never checked. Drive moves a file by editing
    # this list, so "where is it now" has to be answerable after an update - and answerable
    # correctly, not plausibly.
    parents: tuple[str, ...] | None = None
    # Bytes, for an UPLOADED file. `None` means NOT KNOWN, exactly as `parents` above means
    # not asked - Drive omits `size` for native Google files, which have no byte length until
    # they are exported. Reporting 0 would assert a fact never checked, and a size guard that
    # read 0 as "tiny" would wave through the very files it exists to stop.
    size_bytes: int | None = None
    _backend: Backend | None = None
    _read_only: bool = False

    @property
    def type(self) -> str | None:
        return MIME_TO_TYPE.get(self.mime_type)

    @property
    def openable(self) -> bool:
        return self.type is not None

    def open(self) -> Document:
        """Fetch this file as a typed `Doc`/`Sheet`/`Slides`."""
        if self._backend is None:
            raise exc.DetachedError("this FileRef has no backend; obtain one from workspace.files")
        from .workspace import Workspace
        return Workspace(self._backend, read_only=self._read_only).open(self.id)

    def __repr__(self) -> str:
        # Redacted, like the comment models: a file *title* can be as sensitive as its
        # contents ("2026 Layoff Plan"), and embedders log these objects. The name is
        # available as an attribute; it just does not go into a log by accident.
        return (f"FileRef(id={self.id!r}, type={self.type!r}, "
                f"name_chars={len(self.name)})")


def _parse_size(value: Any) -> int | None:
    """Drive returns `size` as a decimal STRING, and omits it for native files.

    Returned as an int so a caller can compare it. A `>` against the raw string would either
    raise or compare lexicographically - "9" > "10000000" - which is the worse failure because
    it looks like it works.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):      # a shape Drive has never sent; unknown beats wrong
        return None


class FileCollection:
    """`workspace.files` — search and recency, paginated lazily.

    Deliberately not a cache. Accessors re-fetch per call, as everywhere else here: this
    tool is used in live multi-reviewer sessions where a self-invalidated cache goes stale
    and reports confidently wrong answers.
    """

    def __init__(self, backend: Backend, read_only: bool = False):
        self._backend = backend
        self._read_only = read_only

    def _wrap(self, raw: dict[str, Any]) -> FileRef:
        # `parents` only when the response carried the key at all - absent means the call did
        # not request it, which is not the same as a file with no parents.
        parents = tuple(raw["parents"]) if "parents" in raw else None
        return FileRef(id=raw["id"], name=raw.get("name", ""),
                       mime_type=raw.get("mimeType", ""), url=raw.get("webViewLink", ""),
                       modified_time=_parse_time(raw.get("modifiedTime")),
                       parents=parents, size_bytes=_parse_size(raw.get("size")),
                       _backend=self._backend, _read_only=self._read_only)

    def search(self, query: str, *, limit: int = 25,
               order_by: str | None = None) -> list[FileRef]:
        """Find files with a Drive query string.

        `query` is Drive's own `q` syntax — `name contains 'x'`, `fullText contains 'y'`,
        `mimeType = '...'`, `modifiedTime > '2026-01-01'`, `'me' in owners`, `sharedWithMe`,
        combined with `and` / `or` / `not`.

        `trashed = false` is appended unless the query mentions `trashed`, because
        `files.list` otherwise returns items already in the bin.
        """
        if not query or not query.strip():
            raise ValueError("query must not be empty; use list_recent() for a bare listing")
        return self._page(self._compose(query), limit, self._order(order_by))

    def recent(self, *, limit: int = 10, order_by: str = "recency") -> list[FileRef]:
        """Recently touched files. `order_by` is `recency`, `lastModified` or `lastModifiedByMe`."""
        return self._page("trashed = false", limit, self._order(order_by) or ORDER_BY["recency"])

    def get(self, file_id_or_url: str) -> FileRef:
        """One file, WHATEVER its type — a Doc, a folder, a PDF, a .docx.

        Deliberately on the account axis rather than through `Workspace.open()`, for the reason
        `update` and `trash` are here: `open()` MIME-dispatches on a three-entry table and
        raises for anything else, so *"what is this file?"* — pure metadata, nothing parsed —
        used to fail on a PDF that `search` had just returned. Search and identify now agree.
        """
        from .workspace import parse_file_id
        return self._wrap(self._backend.get_file_metadata(parse_file_id(file_id_or_url)))

    def download(self, file_id_or_url: str) -> bytes:
        """Raw bytes of an UPLOADED file, unconverted (`alt=media`).

        Not `export`, which is Drive's Google-native conversion and refuses a file it did not
        create. Reading TEXT out of these stays unsupported on purpose - that means parsing an
        untrusted binary format in-process, on the read path `SECURITY.md` calls the primary
        risk. Handing the bytes over parses nothing, which is why this is safe and text
        extraction is not.
        """
        from .workspace import parse_file_id
        return self._backend.download_file(parse_file_id(file_id_or_url))

    def create(self, name: str, kind: str, *, parent_id: str | None = None,
               content: str | None = None) -> FileRef:
        """Create a new file. `kind` is `document`, `spreadsheet`, `presentation` or `folder`.

        With `content`, the text is uploaded as Markdown and Drive converts it — so headings,
        lists, tables and links become real document structure rather than literal `#`
        characters. That is the other half of the Markdown round-trip: `Doc.as_markdown()` out,
        this in. Only meaningful for `document`.
        """
        mime = KINDS.get(kind)
        if mime is None:
            raise ValueError(f"kind must be one of {sorted(KINDS)}, not {kind!r}")
        if content is not None and kind != "document":
            raise ValueError(f"content is only supported for documents, not {kind}s")
        payload = content.encode("utf-8") if content is not None else None
        raw = self._backend.create_file(
            name, mime, parent_id=parent_id, content=payload,
            content_mime_type="text/markdown" if payload is not None else None)
        return self._wrap(raw)

    def copy(self, file_id_or_url: str, *, name: str | None = None,
             parent_id: str | None = None) -> FileRef:
        """Duplicate a file. The copy is a new file with a new id."""
        from .workspace import parse_file_id
        return self._wrap(self._backend.copy_file(
            parse_file_id(file_id_or_url), name=name, parent_id=parent_id))


    # -- lifecycle: any file, including folders -----------------------------
    #
    # These live on the account axis rather than on Document deliberately. `Workspace.open()`
    # MIME-dispatches to Doc / Sheet / Slides and refuses anything else, which is right for
    # content but wrong here: renaming, trashing and sharing are uniform Drive operations that
    # apply to a folder, a PDF or a shortcut just as much as to a document.
    #
    # The demonstration found this by trying to tidy up after itself and being told
    # "unsupported file type" for the folder it had just created.

    def update(self, file_id_or_url: str, *, name: str | None = None,
               parent_id: str | None = None,
               remove_parent_id: str | None = None) -> FileRef:
        """Rename a file or move it between folders. Metadata only, any file type.

        Drive moves by editing a parent list rather than by taking a destination, so
        `parent_id` alone ADDS a parent and the file then lives in both places. Pass
        `remove_parent_id` to move rather than to add.
        """
        from .workspace import parse_file_id
        if name is not None and not name.strip():
            raise ValueError("a file name cannot be empty")
        return self._wrap(self._backend.update_file_metadata(
            parse_file_id(file_id_or_url), name=name, add_parent=parent_id,
            remove_parent=remove_parent_id))

    def trash(self, file_id_or_url: str, *, untrash: bool = False) -> dict:
        """Move a file to the trash, or restore it. Any file type, including folders.

        Recoverable: Drive keeps a trashed file for 30 days. Trashing a FOLDER does not trash
        what is inside it - the children are left loose in My Drive - so anything that tidies
        up after itself has to remove the children first.
        """
        from .workspace import parse_file_id
        return self._backend.trash_file(parse_file_id(file_id_or_url), trashed=not untrash)

    def share(self, file_id_or_url: str, email: str, role: str = "reader", *,
              notify: bool = True) -> Permission:
        """Grant access to any file, including a folder. See `PermissionsMixin.share`."""
        from .permissions import ROLES, Permission
        from .workspace import parse_file_id
        if role == "owner":
            raise ValueError(
                "share() will not transfer ownership; use the Drive UI deliberately. "
                "Pass 'writer' to grant full edit access.")
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; expected one of {', '.join(ROLES)}")
        if not email or "@" not in email:
            raise ValueError(f"expected an email address, got {email!r}")
        return Permission.from_api(self._backend.create_permission(
            parse_file_id(file_id_or_url), email=email, role=role, notify=notify))

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _compose(query: str) -> str:
        return query if "trashed" in query else f"({query}) and trashed = false"

    @staticmethod
    def _order(order_by: str | None) -> str | None:
        """Only the three documented keys. Forwarding an arbitrary string to Drive's
        `orderBy` just converts a typo into a 400 the caller cannot read."""
        if order_by is None:
            return None
        try:
            return ORDER_BY[order_by]
        except KeyError:
            raise ValueError(f"order_by must be one of {sorted(ORDER_BY)}") from None

    def _page(self, query: str, limit: int, order_by: str | None) -> list[FileRef]:
        """Walk pages until `limit` hits or Drive runs out. Drive caps a page at 100."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        found: list[FileRef] = []; token: str | None = None
        while len(found) < limit:
            page = self._backend.search_files(
                query, page_size=min(MAX_PAGE_SIZE, limit - len(found)),
                order_by=order_by, page_token=token)
            found.extend(self._wrap(f) for f in page.get("files", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return found[:limit]
