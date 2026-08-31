import logging
import re
from typing import TYPE_CHECKING

from .. import _cellmap
from .. import exceptions as exc
from ..base import Document

if TYPE_CHECKING:
    from ..comments import Comment

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DEFAULT_RANGE = "A1:Z1000"   # fallback for as_text() when no tab metadata is available

log = logging.getLogger(__name__)


class Sheet(Document):
    """Google Sheets. Comment->A1 cell mapping is best-effort (XLSX export + match)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cell_map_cache = None

    @property
    def tabs(self) -> list[str]:
        """Tab titles, in sheet order. Kept returning plain strings - it is public API and the
        commonest question is "what are they called". `tab_details` has the rest."""
        return [tab["title"] for tab in self.tab_details]

    @property
    def tab_details(self) -> list[dict]:
        """Each tab as `{title, sheet_id, index, hidden, type}`.

        `hidden` is the one worth having: **a hidden tab still exists, still holds data, and
        still occupies its name.** A register build that adds a `Title` tab without knowing a
        hidden one is already called that gets a refusal it cannot explain. `sheet_id` is here
        because `delete_tab` needs the numeric id, never the title.
        """
        ss = self._backend.get_spreadsheet(self.id)
        out = []
        for sheet in ss.get("sheets", []):
            props = sheet.get("properties", {})
            out.append({"title": props.get("title", ""),
                        "sheet_id": props.get("sheetId"),
                        "index": props.get("index"),
                        # Absent means false: Google omits `hidden` on a visible sheet rather
                        # than sending false, so `.get` without a default would give None and a
                        # caller testing truthiness would be right by accident.
                        "hidden": bool(props.get("hidden", False)),
                        "type": props.get("sheetType")})
        return out

    def add_tab(self, name: str, index: int | None = None) -> dict:
        """Add a tab. **Refuses a duplicate name rather than creating `name 2`.**

        Google's own behaviour on a clash is to invent `Title 2`, silently. That is the wrong
        default for anything re-runnable: a caller building a register a second time needs
        *already there* told apart from *created*, and a silently-renamed tab means the next
        write goes to a tab nobody meant.

        The check is case-insensitive because Sheets treats tab names that way in A1 references,
        so `title` and `Title` would collide at use rather than at creation.
        """
        self._require_writable()
        existing = {t["title"].casefold(): t["title"] for t in self.tab_details}
        clash = existing.get(name.casefold())
        if clash is not None:
            raise exc.ConflictError(
                f"a tab named {clash!r} already exists in this spreadsheet"
                + (f" (you asked for {name!r})" if clash != name else "")
                + ". Nothing was created; use it, or choose another name.")
        self._cell_map_cache = None
        return self._backend.sheets_add_tab(self.id, name, index)

    def delete_tab(self, name: str) -> None:
        """Delete a tab **by name**, resolving it to the numeric id Google requires.

        Requires `content.delete`, not `content.write`: this removes every cell in the tab, with
        no trash and no undo through the API. Google refuses to delete the only tab in a
        spreadsheet, and so does this.
        """
        self._require_writable()
        for tab in self.tab_details:
            if tab["title"].casefold() == name.casefold():
                break
        else:
            raise exc.NotFoundError(
                f"no tab named {name!r}; present: {[t['title'] for t in self.tab_details]}")
        self._cell_map_cache = None
        self._backend.sheets_delete_tab(self.id, tab["sheet_id"])

    def values(self, a1_range: str) -> list:
        return self._backend.get_values(self.id, a1_range)

    def _quote_tab(self, title: str) -> str:
        # In A1 notation a tab name may go unquoted only if it reads as a plain
        # identifier (leading ASCII letter/underscore, then ASCII word chars) AND is
        # not itself a cell reference like "A1". Everything else — all-digit ("2024"),
        # leading-digit, spaces, non-ASCII — must be single-quoted (with '' escaping),
        # or Sheets rejects the range with a 400.
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", title) and not re.fullmatch(r"[A-Za-z]{1,3}\d+", title):
            return title
        return "'" + title.replace("'", "''") + "'"

    def _gid(self, title=None):
        sheets = self._backend.get_spreadsheet(self.id).get("sheets", [])
        for s in sheets:
            props = s.get("properties", {})
            if title is None or props.get("title") == title:
                return props.get("sheetId", 0)
        return 0

    @staticmethod
    def _render(rows: list) -> str:
        return "\n".join("\t".join(str(c) for c in row) for row in rows)

    def as_text(self, tab: str | None = None) -> str:
        """Plain text of the grid. By default renders **every** tab (multi-tab sheets are
        not silently truncated), each prefixed with a `# <tab>` header when there's more
        than one. Pass `tab=` to render a single tab (no header)."""
        tabs = self.tabs
        if not tabs:                       # no sheet metadata: fall back to a default range
            return self._render(self._backend.get_values(self.id, _DEFAULT_RANGE))
        if tab is not None:
            if tab not in tabs:
                raise ValueError(f"tab {tab!r} not found; available: {tabs}")
            return self._render(self._backend.get_values(self.id, self._quote_tab(tab)))
        parts = []
        for t in tabs:
            body = self._render(self._backend.get_values(self.id, self._quote_tab(t)))
            parts.append(f"# {t}\n{body}" if len(tabs) > 1 else body)
        return "\n\n".join(parts)

    def create_comment(self, content: str, cell: str | None = None) -> "Comment":
        self._require_writable()
        self._cell_map_cache = None
        if cell is None:
            return super().create_comment(content)
        gid = self._gid()
        link = f"{self.url.split('/edit')[0]}/edit#gid={gid}&range={cell}"
        return super().create_comment(f"{content}\n\n{link}")

    def _cell_map(self) -> dict:
        if self._cell_map_cache is not None:
            return self._cell_map_cache
        import xml.etree.ElementTree as _ET  # nosec B405 - ParseError type only; parsing via defusedxml
        import zipfile

        from defusedxml.common import DefusedXmlException
        from googleapiclient.errors import HttpError

        from ..comments import Comment
        from ..exceptions import CsaWorkspaceError
        try:
            xlsx = self._backend.export_file(self.id, _XLSX)
            roots = _cellmap.parse_xlsx_comments(xlsx)
            raw = self._backend.list_comments(self.id, include_deleted=False)
        except (CsaWorkspaceError, HttpError, zipfile.BadZipFile,
                _ET.ParseError, DefusedXmlException) as e:
            # transient/malformed/malicious/export-cap: degrade to location=None WITHOUT
            # memoizing (so a later call retries), and record why so callers can tell this
            # apart from a genuine no-match (spec §8: location=None + a recorded warning).
            log.warning("cell mapping unavailable for sheet %s (%s: %s); "
                        "comments will have location=None", self.id, type(e).__name__, e)
            return {}
        comments = [Comment.from_api(d) for d in raw]
        self._cell_map_cache = _cellmap.match_locations(comments, roots)   # pure; a bug here propagates
        return self._cell_map_cache

    def _locate_comment(self, raw: dict):
        return self._cell_map().get(raw.get("id"))

    def comments_by_cell(self, cell: str, tab: str | None = None) -> list:
        """Comments anchored at `cell`, optionally narrowed to a single tab.

        `tab=None` keeps the pre-#290 behaviour: every tab, which on a multi-tab workbook can
        return comments about different sheets that share a cell reference. Callers that care
        should read `Comment.location.tab`, which is now populated wherever the sheet could be
        resolved from the export.

        A comment whose tab could NOT be resolved (`location.tab is None`) is excluded when a
        tab is named. It might be on that tab; saying so would be a guess, and this method's
        contract is "comments I can place here", not "comments that might be here".
        """
        wanted = self.resolve_tab(tab) if tab is not None else None
        found = []
        for comment in self.comments.all():
            location = comment.location
            if not location or location.cell != cell:
                continue
            if wanted is not None and location.tab != wanted:
                continue
            found.append(comment)
        return found

    def resolve_tab(self, tab: str) -> str:
        """The real tab title matching `tab`. **Raises rather than returning nothing.**

        Case-insensitive and whitespace-tolerant, following `add_tab`: Sheets treats tab names
        that way in A1 references, so `budget` and `Budget` would collide at use anyway.

        **An unknown name is refused, not answered with an empty result**, and the consumer is
        why. For a model the tool result *is* the world - it has no tab bar to glance at - so an
        empty list for a misspelled tab is a well-formed wrong answer with no correction path.
        Worse, it acts as a silent precondition check: *no comments on B11* is exactly what
        something checks before overwriting B11, so a typo becomes a data-loss authorisation.
        The refusal costs one call and carries the fix, because it names the tabs that exist.

        Public because the MCP layer needs the same resolution to report honestly, and because
        duplicating this comparison is how the two layers would drift apart.
        """
        wanted = tab.strip().casefold()
        for detail in self.tab_details:
            if detail["title"].casefold() == wanted:
                return str(detail["title"])
        raise exc.NotFoundError(
            f"no tab named {tab!r} in this spreadsheet; present: "
            f"{[d['title'] for d in self.tab_details]}")

    def reload(self) -> None:
        self._cell_map_cache = None

    def update(self, a1_range: str, values: list, value_input_option: str = "RAW") -> None:
        self._require_writable()
        self._cell_map_cache = None
        self._backend.sheets_values_update(self.id, a1_range, values, value_input_option)

    def append_rows(self, a1_range: str, values: list, value_input_option: str = "RAW") -> None:
        """Append rows after the last row of the table that `a1_range` falls in
        (Sheets `values.append`, `INSERT_ROWS`). Non-idempotent — never auto-retried."""
        self._require_writable()
        self._cell_map_cache = None
        self._backend.sheets_values_append(self.id, a1_range, values, value_input_option)

    def clear(self, a1_range: str) -> None:
        self._require_writable()
        self._cell_map_cache = None
        self._backend.sheets_values_clear(self.id, a1_range)

    def batch_update(self, requests: list) -> dict:
        self._require_writable()
        self._cell_map_cache = None
        return self._backend.sheets_batch_update(self.id, requests)
