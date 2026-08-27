"""Apply a filled-in comment register back to the document.

The export makes 205 threads readable; this makes them actionable. It is also a **bulk mutation
of a shared document driven by a file**, which is a far sharper thing than an export, so most of
what follows is about the ways that goes wrong.

**Two layers of idempotency, because one is not enough.**

The obvious protection is a `*_completed` column ticked as each row is applied, so a re-run
skips finished work. That covers the ordinary case and fails in precisely the interesting one:
the reply posts, and the process dies *before* the tick is written. The sheet then says
not-done while the document says done, and a re-run trusting the marker alone posts the reply
twice — to a thread forty-two people are reading, with no way to unsend it.

So the marker is the **fast path** and the live document is the **authority**. Before posting,
look for a reply carrying this exact text, from this user, already on the thread. There is no
real reason to post a completely identical reply twice, so an exact match is treated as
evidence the work was already done — and `force` exists for whoever genuinely means it.

Resolve needs none of that: `resolved` *is* the state, so an already-resolved thread is skipped
on its own evidence.

**Everything is dry-run unless `apply` is set.** The blast radius is somebody's review, under
their name, and a spreadsheet is easy to get subtly wrong — a sort that did not carry every
column, a fill-down that overshot.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._export import ACTIONS, COLUMNS, COMPLETED, XLSX_SUFFIX

DONE = "yes"
# Deliberately a closed set. "maybe later" in a resolve column must FAIL rather than be
# guessed at: guessing wrong closes somebody's open question.
TRUE = {"true", "yes", "y", "1", "x", "done", "✓"}
FALSE = {"false", "no", "n", "0", ""}


@dataclass
class RowResult:
    thread_id: str
    replied: bool = False
    resolved: bool = False
    failed: bool = False
    detail: str = ""


@dataclass
class Report:
    rows: list[RowResult] = field(default_factory=list)
    applied: bool = False

    def count(self, attr: str) -> int:
        return sum(1 for r in self.rows if getattr(r, attr))


def _norm(text: Any) -> str:
    """Whitespace-insensitive, because a spreadsheet cell round-trips with stray space."""
    return " ".join(str(text or "").split())


def truthy(value: Any) -> bool | None:
    """True / False / None, where None means "not a value I will guess at"."""
    text = _norm(value).lower()
    if text in TRUE:
        return True
    if text in FALSE:
        return False
    return None


def read_rows(path: Path) -> list[dict]:
    """The register back, from .csv or .xlsx."""
    if path.suffix.lower() == XLSX_SUFFIX:
        try:
            from openpyxl import load_workbook
        except ImportError as e:                  # pragma: no cover - environment-dependent
            raise ValueError("reading .xlsx needs openpyxl: pip install "
                             "'csa-google-workspace[xlsx]'") from e
        ws = load_workbook(path, data_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h) if h is not None else "" for h in next(it, ())]
        # strict=False: a spreadsheet row may be short where trailing cells were never
        # touched, and a missing cell is an empty one, not a corrupt file.
        return [dict(zip(header, ["" if v is None else v for v in row], strict=False))
                for row in it]
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_back(path: Path, rows: list[dict], header: list[str]) -> None:
    """Rewrite the register with the completed markers, atomically.

    Temp file plus rename, because the whole point of the markers is surviving a crash, and a
    half-written register would be a worse state than the one being protected against.
    """
    if path.suffix.lower() == XLSX_SUFFIX:
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb.active
        head = [c.value for c in next(ws.iter_rows(max_row=1))]
        index = {name: i for i, name in enumerate(head)}
        # strict=False deliberately: this runs AFTER the actions have been applied, so a
        # length mismatch must not raise and lose the report. The markers are the fast path
        # anyway - the document check is what actually prevents a double-post.
        for row_cells, row in zip(ws.iter_rows(min_row=2), rows, strict=False):
            for name in COMPLETED:
                if name in index and row.get(name):
                    row_cells[index[name]].value = row[name]
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=XLSX_SUFFIX,
                                         delete=False) as tmp:
            wb.save(tmp.name)
            os.replace(tmp.name, path)
        return
    with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".csv", delete=False,
                                     newline="", encoding="utf-8") as tmp:
        writer = csv.DictWriter(tmp, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in header})
        os.replace(tmp.name, path)


def _mine_already_said(comment: Any, text: str) -> bool:
    """Has THIS user already posted this exact reply on this thread?

    Author-aware on purpose. The same text from somebody else is not evidence that I did the
    work - two reviewers can legitimately write "Fixed." - whereas my own identical reply
    almost certainly means the previous run got there and died before ticking the box.
    """
    wanted = _norm(text)
    for reply in (comment.replies or []):
        author = getattr(reply, "author", None)
        if getattr(author, "is_me", False) and _norm(reply.content) == wanted:
            return True
    return False


def apply_rows(document: Any, rows: list[dict], *, apply: bool, force: bool) -> Report:
    """Walk the register once. Never raises for one bad row — 205 rows and #113 failing must
    not cost the other 204."""
    report = Report(applied=apply)
    by_id = {c.id: c for c in document.comments.all()}

    for row in rows:
        thread = _norm(row.get("thread_id"))
        result = RowResult(thread_id=thread)
        reply_text = str(row.get("reply_comment") or "").strip()
        resolve_raw = row.get("resolve_comment")
        wants_resolve = truthy(resolve_raw)

        notes: list[str] = []
        try:
            if _norm(row.get("reply_to")):
                # Drive replies are flat: you reply to a THREAD, never to a reply. A filled-in
                # reply row is somebody working on the wrong line.
                if reply_text or wants_resolve:
                    raise ValueError(
                        "this row is a reply (reply_to is set), and actions belong on the "
                        "thread's own row - Drive has no reply-to-a-reply")
                notes.append("a reply row; nothing to do")
            elif not reply_text and not wants_resolve and wants_resolve is not None:
                notes.append("nothing filled in")
            else:
                # The row's own validity first: an unreadable resolve value is wrong whether
                # or not the thread exists, and "maybe later" must fail rather than be guessed
                # at - guessing wrong closes somebody's open question.
                if wants_resolve is None:
                    raise ValueError(
                        f"resolve_comment is {str(resolve_raw)!r}, which is neither true nor "
                        f"false. Use true/yes/1 or leave it empty - a value nobody can read "
                        f"is not something to guess at when the result closes a thread.")
                # Reaching here means there IS something to do, so a missing thread is an
                # error unconditionally. (The earlier version guarded this with an `and`,
                # which was true but too subtle for a reader or a type checker to follow.)
                comment = by_id.get(thread)
                if comment is None:
                    raise ValueError(f"no comment {thread!r} on this file")

                # Reply BEFORE resolve: resolving posts its own visible action-reply, so the
                # substantive one has to land first or the thread reads backwards.
                if reply_text:
                    if truthy(row.get("reply_comment_completed")):
                        notes.append("reply already marked done")
                    elif not force and _mine_already_said(comment, reply_text):
                        # The crash case: posted, then died before the tick.
                        notes.append("an identical reply from you is already on this thread; "
                                     "skipped (pass force to post it anyway)")
                        row["reply_comment_completed"] = DONE
                    elif apply:
                        comment.reply(reply_text)
                        row["reply_comment_completed"] = DONE
                        result.replied = True
                        notes.append("replied")
                    else:
                        result.replied = True
                        notes.append("would reply")

                if wants_resolve:
                    if comment.resolved:
                        notes.append("already resolved")
                        row["resolve_comment_completed"] = DONE
                    elif truthy(row.get("resolve_comment_completed")):
                        notes.append("resolve already marked done")
                    elif apply:
                        comment.resolve()
                        row["resolve_comment_completed"] = DONE
                        result.resolved = True
                        notes.append("resolved")
                    else:
                        result.resolved = True
                        notes.append("would resolve")
        except Exception as error:                # noqa: BLE001 - reported, never fatal
            result.failed = True
            result.replied = result.resolved = False
            notes = [f"{type(error).__name__}: {error}"]

        result.detail = "; ".join(notes) or "nothing to do"
        report.rows.append(result)
    return report


def header_for(rows: list[dict]) -> list[str]:
    """The sheet's own column order, extended with anything we must write back."""
    seen = list(rows[0]) if rows else list(COLUMNS)
    for name in (*ACTIONS, *COMPLETED):
        if name not in seen:
            seen.append(name)
    return seen
