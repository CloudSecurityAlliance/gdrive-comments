"""Comment export: flat rows, ready for a spreadsheet or for another tool entirely.

Two audiences, and **neither of them is an AI**, which is the reason this exists rather than
leaving people to compose three tools:

- somebody who would rather work in a **spreadsheet**. A register of every thread, with the text
  each one is about, is how document review has always been done, and this makes that better
  rather than obsolete.
- **another tool** — a notebook, a BI query, `grep`. Flat rows with a thread id feed anything;
  nested JSON does not.

**Flat, one row per comment AND per reply**, with `reply_to` naming the thread. That is the
lossless shape: one-row-per-thread is a trivial group-by away, and the reverse is not recoverable.
`columns` is returned in order so writing a sheet is a loop rather than a judgement call.

The interesting part is the last column, and it is per-type, because *what a comment points at*
is a different fact for each:

    Docs     `quoted_text`  - the passage, from Drive's quotedFileContent
    Sheets   `cell_text`    - what the cell actually HOLDS. A comment on B11 is meaningless in
                              a register unless the register also says B11 is "Q3 revenue".

And the Sheets half produces an unexpected answer to the multi-tab problem (TODO.md D3). We
cannot know which tab a comment is on — the XLSX export carries no correlation from a
`threadedComments` member back to a sheet name. But we can report that cell **on every tab**,
and the *content* then tells a human which it was: if B11 is empty on Summary and reads
"Q3 revenue" on Detail, the comment is about Detail. That resolves the ambiguity in practice
without the code guessing, which beats both guessing and refusing.
"""
from __future__ import annotations

from typing import Any

COLUMNS = ("thread_id", "reply_to", "author", "created_time", "resolved", "text",
           "quoted_text", "cell", "cell_text", "cell_text_by_tab")


def _row(**kw: Any) -> dict[str, Any]:
    """Every row carries every column, so a spreadsheet write never has ragged rows."""
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    row.update(kw)
    return row


def _cell_lookup(document: Any) -> tuple[dict[str, list[list[Any]]], list[str]]:
    """({tab: grid}, tabs) for a spreadsheet; ({}, []) for anything else.

    One read per tab, done once for the whole export rather than once per comment - a register
    of forty comments must not be forty API calls.
    """
    tabs = list(getattr(document, "tabs", []) or [])
    if not tabs:
        return {}, []
    grids: dict[str, list[list[Any]]] = {}
    for tab in tabs:
        try:
            grids[tab] = document.values(tab) or []
        except Exception:                       # noqa: BLE001 - a tab we cannot read is not
            grids[tab] = []                     # a reason to fail the whole export
    return grids, tabs


def _at(grid: list[list[Any]], row: int, col: int) -> str:
    """The text at 1-based (row, col), or "" — which is what an empty cell holds.

    Empty rather than None on purpose: a cell inside the sheet with nothing in it *is* empty,
    and a register that prints "None" there is reporting a different fact.
    """
    if row < 1 or col < 1 or row > len(grid):
        return ""
    line = grid[row - 1] or []
    return "" if col > len(line) else str(line[col - 1])


def comment_rows(document: Any, comments: list) -> tuple[list[str], list[dict], list[str]]:
    """(columns, rows, caveats)."""
    grids, tabs = _cell_lookup(document)
    caveats: list[str] = []
    if len(tabs) > 1:
        caveats.append(
            f"This workbook has {len(tabs)} tabs ({', '.join(tabs)}) and Google's export gives "
            f"no way to tell which tab a comment is on, so there is no tab column. "
            f"`cell_text_by_tab` shows what that cell holds on each tab instead - the content "
            f"usually makes it obvious which one a comment was about.")

    rows: list[dict] = []
    for comment in comments:
        location = getattr(comment, "location", None)
        cell = getattr(location, "cell", None) if location else None
        cell_text = None
        by_tab = None
        if cell and grids:
            row_i = getattr(location, "row", 0)
            col_i = getattr(location, "col", 0)
            per_tab = {tab: _at(grid, row_i, col_i) for tab, grid in grids.items()}
            if len(tabs) == 1:
                cell_text = per_tab[tabs[0]]
            else:
                by_tab = per_tab

        author = getattr(comment.author, "display_name", None) if comment.author else None
        rows.append(_row(thread_id=comment.id, reply_to=None, author=author,
                         created_time=_iso(getattr(comment, "created_time", None)),
                         resolved=bool(comment.resolved), text=comment.content,
                         quoted_text=getattr(comment, "quoted_text", None),
                         cell=cell, cell_text=cell_text, cell_text_by_tab=by_tab))
        for reply in (comment.replies or []):
            reply_author = (getattr(reply.author, "display_name", None)
                            if getattr(reply, "author", None) else None)
            # A reply carries no passage and no cell of its own: only the top-level comment
            # anchors, and repeating the thread's anchor on every reply would make a register
            # look like several separate findings.
            rows.append(_row(thread_id=reply.id, reply_to=comment.id, author=reply_author,
                             created_time=_iso(getattr(reply, "created_time", None)),
                             resolved=bool(comment.resolved), text=reply.content))
    return list(COLUMNS), rows, caveats


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


# ── Destinations ────────────────────────────────────────────────────────────────────────
#
# "Here are some rows" saves nobody an hour. The two things a person actually wants are a CSV
# they can open and a Sheet they can share, so both are first-class rather than left to the
# caller to assemble.

CSV_SUFFIX = ".csv"


def flatten(value: Any) -> str:
    """One CSV cell's worth of text.

    `cell_text_by_tab` is a dict, and a CSV cell reading `{'Summary': '42'}` is not something a
    person can read - so it renders as `Summary=42 | Detail=Q3 revenue`, which is legible in a
    spreadsheet column and still says which tab held what.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return " | ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def to_csv(columns: list[str], rows: list[dict]) -> str:
    """RFC 4180 via the stdlib, so quoting and embedded newlines are somebody else's problem.

    `\r\n` because that is what `csv` writes by default and what Excel expects; Sheets and
    every other reader cope with it.
    """
    import csv as _csv
    import io
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([csv_safe(flatten(row.get(c))) for c in columns])
    return buf.getvalue()


def to_grid(columns: list[str], rows: list[dict]) -> list[list[str]]:
    """Header row plus data, for a Sheets `values.update`."""
    return [list(columns)] + [[flatten(row.get(c)) for c in columns] for row in rows]


# ── Formula injection ───────────────────────────────────────────────────────────────────
#
# A comment on a shared document can begin with `=`, `+`, `-` or `@`, and Excel reads such a
# cell as a FORMULA when the file is opened - `=cmd|' /C calc'!A0` being the classic DDE
# payload. Anyone who can comment on a document we share can plant it, and the whole point of
# this feature is that a human opens the result in a spreadsheet. So this is not a theoretical
# concern here; it is the primary risk in SECURITY.md arriving by a new route.
#
# v0.24.0 shipped the CSV without this escape. The remedy is OWASP's: a leading apostrophe,
# which Excel and Sheets both read as "the rest is text" while leaving the value legible.
#
# NOT applied to `to_grid`: a Sheets write uses RAW, which stores values as text without
# parsing, so a leading `=` is already inert - and escaping there would put a stray apostrophe
# into somebody's spreadsheet.
FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(text: str) -> str:
    return "'" + text if text[:1] in FORMULA_LEAD else text


def _slug(name: str) -> str:
    """A document title reduced to something usable as a filename.

    Titles are untrusted - somebody can name a Doc `../../etc/passwd` - so this keeps only
    characters that cannot mean anything to a path, and never returns empty.
    """
    keep = [c if (c.isalnum() or c in " -_") else " " for c in (name or "")]
    slug = " ".join("".join(keep).split())[:60].strip(" .-_")
    return slug or "comments"


def resolve_export_path(path: str | None, *, default_dir: str | None, doc_name: str,
                        stamp: str, suffix: str = CSV_SUFFIX):
    """(target, a sentence saying what happened) — or `ValueError` saying why not.

    A full path is ALLOWED, deliberately. A Claude Desktop *project* may only be able to write
    inside its own folder, where `~/Downloads` is unreachable; a Claude Code user wants the
    register in the repo they are working in. Confining to one directory would break exactly
    the cases where the file is most useful.

    What makes that safe is not validating the path but making every failure mode inert:

      * **nothing is ever overwritten** - an existing target gets `-<stamp>` appended, so the
        worst case is an unexpected file rather than a destroyed one;
      * **the extension is forced to `.csv`** - `~/.zshrc` becomes `~/.zshrc.csv`, which no
        shell will read;
      * **directories are never created**, so a path cannot conjure a tree;
      * the caller reports the resolved absolute path, because visibility is the last control.
    """
    from pathlib import Path
    given = (path or "").strip()
    told_where = False

    if not given:
        given = f"{_slug(doc_name)} comments {stamp}{suffix}"
        told_where = True
    has_dir = any(sep in given for sep in ("/", "\\")) or given.startswith("~")
    if has_dir:
        target = Path(given).expanduser()
    else:
        if not default_dir:
            raise ValueError("no default export directory is available; pass a full path")
        target = Path(default_dir).expanduser() / given
        told_where = True

    # `.csv` whatever was asked for. A name with no suffix gets one; a name with the wrong
    # suffix keeps it and gains ours, so `.zshrc` -> `.zshrc.csv` rather than `.csv`, which
    # would silently rename somebody's intended file.
    if target.suffix.lower() != suffix:
        target = target.with_name(target.name + suffix)

    parent = target.parent.expanduser()
    if not parent.is_dir():
        raise ValueError(
            f"{parent} does not exist or is not a directory, and directories are not created "
            f"automatically. Pass a full path to somewhere that exists, or use "
            f'destination="csv" to get the text back instead.')
    target = (parent.resolve() / target.name)

    note = ""
    if target.exists():
        target = target.with_name(f"{target.stem}-{stamp}{suffix}")
        note = (f"A file of that name already existed, so this was written as "
                f"{target.name} instead - nothing was overwritten. ")
    if told_where:
        note += f"Written to {target}. "
    return target, note


# ── Excel ───────────────────────────────────────────────────────────────────────────────
#
# A register somebody works through, rather than a CSV they have to import first. Asked for
# one, the honest answer used to be "CSV, a Google Sheet, or rows", and converting by hand hit
# two things the tool should handle - so it does.

XLSX_SUFFIX = ".xlsx"
HEADER_FILL = "1F3864"

# openpyxl refuses to write these and raises IllegalCharacterError. Reviewer text is arbitrary
# human input - pasted from terminals, editors, mail clients - so it genuinely contains them: a
# real 205-comment review had one. A register that will not be written because somebody pasted
# from a terminal is no register at all.
_ILLEGAL = "".join(chr(c) for c in list(range(0, 9)) + [11, 12] + list(range(14, 32)))
_STRIP = str.maketrans("", "", _ILLEGAL)


def _sheet_safe(value: Any) -> Any:
    text = flatten(value)
    return text.translate(_STRIP) if text else text


def used_columns(columns: list[str], rows: list[dict]) -> list[str]:
    """Only the columns that carry something.

    On a DOCUMENT the three Sheets-only columns (`cell`, `cell_text`, `cell_text_by_tab`) are
    structurally absent, and three empty columns on a review register suggest the export failed
    to fill them rather than that they do not apply. Computed from the data rather than from
    the file type, so it stays right for a type that has neither.
    """
    if not rows:
        return list(columns)
    return [c for c in columns if any(flatten(row.get(c)) for row in rows)]


def to_xlsx(columns: list[str], rows: list[dict], target, *, title: str) -> None:
    """Write a formatted, immediately usable register.

    **No formulas, deliberately.** openpyxl writes them with no cached values, so anything
    reading cached values - a thumbnail previewer, pandas - sees blanks until Excel opens the
    file and recalculates. A faithful register needs no formulas, so it has none and the
    problem does not arise. Somebody wanting a pivot can build one on top.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as e:                      # pragma: no cover - environment-dependent
        raise ValueError(
            "writing .xlsx needs openpyxl, which is not installed. Either "
            "`pip install 'csa-google-workspace[xlsx]'`, or use destination=\"file\" for a "
            "CSV, which needs nothing extra.") from e

    keep = used_columns(columns, rows)
    wb = Workbook()
    ws = wb.active
    # A tab name may not exceed 31 characters or contain []:*?/\ - and it is derived from a
    # document title, which is untrusted.
    ws.title = ("".join(c for c in title if c not in "[]:*?/\\")[:31] or "Comments")
    ws.append(keep)
    for row in rows:
        ws.append([_sheet_safe(row.get(c)) for c in keep])

    font = "Arial"
    fill = PatternFill("solid", fgColor=HEADER_FILL)
    for cell in ws[1]:
        cell.font = Font(name=font, bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    # Frozen header and an autofilter, because two hundred unsorted rows is not a register.
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 28

    wide = {"text", "quoted_text", "cell_text_by_tab"}
    for i, name in enumerate(keep, start=1):
        letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[letter].width = 62 if name in wide else (
            22 if name in {"author", "created_time"} else 16)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name=font)
            cell.alignment = Alignment(
                vertical="top", wrap_text=keep[cell.column - 1] in wide)
    wb.save(target)
