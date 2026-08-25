"""The write allowlist: which files a capability may touch. #82's second dimension.

**Deliberately the simplest thing that works: a flat list of document URLs.** No folders, no
patterns, no wildcards. Folders are the interesting design problem and they are *not* solved
here — see `TODO.md`, "Folders in the allowlist", for why folder-as-rule is harder and more
dangerous than it looks. Until that is settled, a folder URL in the file is a **loud error**,
not a silently-inert entry.

Enforcement is by **file id**, not by URL string. Every URL form for the same document
normalises to the same id, so a pasted `/edit?tab=t.0` link and a bare id are the same entry —
and a *copy* of an allowlisted document has a different id and is therefore not allowlisted,
which is the correct default.

Format — plain text, one URL per line, `#` starts a comment:

    # CSA WG documents this agent may write to.
    https://docs.google.com/document/d/1oW1BM…/edit?tab=t.0   # CCM v5 mapping, per WG lead
    https://docs.google.com/spreadsheets/d/1abc…/edit          # AICM tracker

Plain text rather than TOML/YAML for three reasons: it reviews like code in a `git diff`, the
trailing comment gives #82's required *reason per entry* for free on the same line, and it
needs no dependency on Python 3.10 (where `tomllib` does not exist). Per-capability scoping —
"this file may be commented on but not edited" — will need a structured format; that is a
deliberate later migration, noted in `TODO.md`.

**Fail closed.** A configured-but-unusable allowlist (missing file, unreadable, no valid
entries, any malformed line) raises rather than degrading to "no restrictions". The failure
mode being avoided is an operator who believes writes are scoped when they are not.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from . import exceptions as exc

log = logging.getLogger(__name__)

# `/d/<id>` covers docs.google.com/{document,spreadsheets,presentation}/d/<id> and
# drive.google.com/file/d/<id>.
_ID_IN_PATH = re.compile(r"/d/([a-zA-Z0-9_-]{10,})")
# The older `?id=` / `&id=` form, still produced by some Drive UI paths.
_ID_IN_QUERY = re.compile(r"[?&]id=([a-zA-Z0-9_-]{10,})")
# What we must refuse rather than misread.
_FOLDER = re.compile(r"/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)")


class AllowlistError(exc.CsaWorkspaceError):
    """The allowlist is configured but unusable. Never degrades to "no restrictions"."""


@dataclass(frozen=True)
class Entry:
    file_id: str
    url: str
    reason: str | None
    line: int

    def __repr__(self) -> str:
        # The reason may name people or projects; the id is what an audit needs.
        return f"Entry(file_id={self.file_id!r}, line={self.line}, has_reason={self.reason is not None})"


def parse_document_url(text: str) -> str:
    """A pasted Drive/Docs URL -> file id.

    Raises `AllowlistError` for anything not a single document, **including folders**. A
    folder URL cannot be treated as an opaque id: it would never match any file, so the
    entry would protect nothing while looking in the file like protection. That silent
    no-op is the exact failure #82 calls dead-entry detection.

    A **bare file id is rejected**, unlike `Workspace.open()`, which accepts one. Two
    reasons, both about review rather than convenience. A bare id cannot be distinguished
    from a typo — Drive ids are unstructured base64url, so `some-long-dashed-name` and a
    real id are the same shape, and an early version of this parser accepted both. And a URL
    in a reviewed config file is *clickable*: someone approving the entry can open it and
    see what they are granting.
    """
    candidate = text.strip()
    if not candidate:
        raise AllowlistError("empty URL")

    folder = _FOLDER.search(candidate)
    if folder:
        raise AllowlistError(
            f"{candidate!r} is a folder, and folders are not supported in the allowlist yet. "
            f"List the individual document URLs inside it instead. (Folder support needs the "
            f"traversal, shortcut and TOCTOU questions settled first — see TODO.md, "
            f"'Folders in the allowlist'.)")

    for pattern in (_ID_IN_PATH, _ID_IN_QUERY):
        found = pattern.search(candidate)
        if found:
            return found.group(1)

    raise AllowlistError(
        f"{candidate!r} is not a Google document URL. Expected something like "
        f"https://docs.google.com/document/d/<id>/edit — a full URL, not a bare file id.")


def parse_allowlist(text: str, *, source: str = "<string>") -> tuple[Entry, ...]:
    """Parse the allowlist format. Every malformed line is reported, not just the first.

    Reporting all of them matters: an operator fixing a curated list of thirty URLs should
    not have to run the server thirty times to find the thirty typos.
    """
    entries: list[Entry] = []
    problems: list[str] = []
    seen: dict[str, int] = {}

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        url, _, comment = line.partition("#")
        reason = comment.strip() or None
        try:
            file_id = parse_document_url(url)
        except AllowlistError as e:
            problems.append(f"  {source}:{number}: {e}")
            continue
        if file_id in seen:
            # Not an error — a duplicate is harmless — but worth saying, because it usually
            # means two URLs someone believed were different documents.
            log.warning("allowlist %s:%d repeats the file already listed on line %d",
                        source, number, seen[file_id])
            continue
        seen[file_id] = number
        entries.append(Entry(file_id=file_id, url=url.strip(), reason=reason, line=number))

    if problems:
        raise AllowlistError(
            f"{len(problems)} unusable line(s) in the allowlist:\n" + "\n".join(problems))
    if not entries:
        raise AllowlistError(
            f"the allowlist at {source} contains no usable entries. Refusing to run with an "
            f"empty allowlist, because that is indistinguishable from a typo'd path and "
            f"would silently permit nothing (or, if ignored, everything).")
    return tuple(entries)


def load_allowlist(path: str) -> tuple[Entry, ...]:
    """Read and validate an allowlist file. Raises `AllowlistError` on any problem."""
    resolved = Path(path).expanduser()
    try:
        text = resolved.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise AllowlistError(
            f"no allowlist file at {resolved}. It was configured, so this is a hard failure "
            f"rather than a fallback to unrestricted writes.") from e
    except OSError as e:
        raise AllowlistError(f"cannot read the allowlist at {resolved}: {e}") from e
    entries = parse_allowlist(text, source=str(resolved))
    log.info("write allowlist loaded from %s: %d file(s)", resolved, len(entries))
    return entries
