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
        writer.writerow([flatten(row.get(c)) for c in columns])
    return buf.getvalue()


def to_grid(columns: list[str], rows: list[dict]) -> list[list[str]]:
    """Header row plus data, for a Sheets `values.update`."""
    return [list(columns)] + [[flatten(row.get(c)) for c in columns] for row in rows]


def safe_export_path(export_dir: str | None, filename: str | None, *, overwrite: bool):
    """Resolve `filename` inside `export_dir`, or raise `ValueError` saying why not.

    This is the only place in the project that writes to the local filesystem, and document
    content is untrusted input, so the constraints are deliberately blunt:

      * no `export_dir` configured -> refused. The operator opts in; a conversation cannot.
      * `filename` is a NAME, not a path. Any separator, any `..`, any `~`, anything absolute
        is refused outright - so the directory cannot be influenced from inside a session.
      * the extension is forced to `.csv`, so even a successful attempt at influencing the name
        writes a CSV rather than a shell profile or a script.
      * no silent overwrite.
      * containment is re-checked AFTER resolution, so a symlink in the export directory
        cannot escape it.
    """
    from pathlib import Path
    if not export_dir:
        raise ValueError(
            "writing a local file is off: set CSA_GW_EXPORT_DIR to a directory to enable it. "
            "Until then, use destination=\"csv\" to get the text back, or "
            "destination=\"sheet\" to write a Google Sheet.")
    base = Path(export_dir).expanduser()
    if not base.is_dir():
        raise ValueError(f"CSA_GW_EXPORT_DIR is {export_dir!r}, which does not exist or is not "
                         f"a directory. It is not created automatically, because a typo should "
                         f"not quietly start writing somewhere unexpected.")
    name = (filename or "comments").strip()
    if not name or name in (".", ".."):
        raise ValueError("filename must be a name, not empty")
    if any(sep in name for sep in ("/", "\\")) or name.startswith("~") or ".." in name:
        raise ValueError(
            f"filename must be ONLY A NAME with no separator, no '..' and no '~' - got "
            f"{name!r}. The directory is CSA_GW_EXPORT_DIR and is the operator's decision, "
            f"not something a request can redirect.")
    if not name.lower().endswith(CSV_SUFFIX):
        name += CSV_SUFFIX
    base = base.resolve()
    target = (base / name).resolve()
    if target.parent != base:
        raise ValueError(f"{name!r} resolves outside CSA_GW_EXPORT_DIR; refusing")
    if target.exists() and not overwrite:
        raise ValueError(f"{target} already exists. Pass overwrite=true to replace it, or "
                         f"choose another name.")
    return target
