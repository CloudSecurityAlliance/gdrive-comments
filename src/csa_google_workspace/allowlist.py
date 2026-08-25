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

**Two scopes, configured independently** — `CSA_GW_ALLOWLIST_READ` and
`CSA_GW_ALLOWLIST_MODIFY`. Reads and mutations are different risks and want different answers:
the common posture is `READ=*` (matching what Google's and Anthropic's Drive servers do, since
the agent already sees whatever the user's credentials see) with `MODIFY` a short, reviewed
list. Splitting them is what makes that expressible.

**`*` means everything, and must be typed.** An unset scope is **fail closed** in the MCP
server: no files, so every operation of that kind is refused with a message saying what to set.
Unrestricted access is available — as a literal `*` entry — but it is a thing somebody chose,
and it logs a warning every time.

**Three ways to configure each**, because they suit different deployments:

* **The default paths** `~/.csa_google_workspace/allowlist-read.txt` and
  `allowlist-modify.txt`, used automatically when they exist — next to
  `client_secret.json`, and for the same reason. A curated list distributed by a
  setup script needs no per-user configuration at all, which matters when the people
  running it did not write it.
* **`CSA_GW_ALLOWLIST_MODIFY=/path/to/file`** — an explicit path.
* **`CSA_GW_ALLOWLIST_MODIFY=<urls>`** — the URLs *inline*, for an MCP client's JSON `env`
  block where shipping a second file is awkward. Any value containing `://` is read as URLs
  rather than a path; a filesystem path does not contain that.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import exceptions as exc

log = logging.getLogger(__name__)

# The one entry that means "no restriction". A literal, because unrestricted access should be
# something a person typed into a reviewed file rather than a default nobody noticed.
ALL = "*"
# Accepted as a synonym so the v0.8.1 spelling keeps working.
ALL_SYNONYMS = frozenset({ALL, "any", "all"})

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
class Listing:
    """A parsed allowlist: either "everything", or a specific set of documents.

    `all_files` is not just `entries == ()`; the two are different answers. An empty listing
    is a configuration error (indistinguishable from a typo), whereas `all_files` is a
    deliberate, logged decision.
    """
    all_files: bool
    entries: tuple[Entry, ...] = ()

    @property
    def file_ids(self) -> frozenset[str]:
        return frozenset(e.file_id for e in self.entries)

    def __repr__(self) -> str:
        return ("Listing(all_files=True)" if self.all_files
                else f"Listing(files={len(self.entries)})")


@dataclass(frozen=True)
class Entry:
    file_id: str
    url: str
    reason: str | None
    line: int

    def __repr__(self) -> str:
        # The reason may name people or projects; the id is what an audit needs.
        return f"Entry(file_id={self.file_id!r}, line={self.line}, has_reason={self.reason is not None})"


PLACEHOLDER_MARKS = ("…", "...", "<", ">", "[", "]", "{", "}", "xxx", "AAA", "BBB")
GOOGLE_HOSTS = ("docs.google.com", "drive.google.com", "sheets.google.com",
                "slides.google.com")


def diagnose_url(text: str) -> str | None:
    """Why `text` is not a usable document URL — or `None` if it is fine.

    Deliberately a ladder of specific cases rather than one "invalid URL". Every rung here
    corresponds to a mistake somebody actually makes, and the difference between "invalid
    value" and "the URL stops after /d/, so the file id is missing" is the difference between
    a support conversation and a fix. Deterministic, so it is testable and cannot be wrong
    about its own diagnosis; the model reading the tool error is what relays it in prose.
    """
    candidate = text.strip()
    if not candidate:
        return "the value is empty"

    if _FOLDER.search(candidate):
        return ("it is a folder, and folders are not supported in the allowlist yet. List the "
                "individual document URLs inside it instead. (Folder support needs the "
                "traversal, shortcut and TOCTOU questions settled first — see TODO.md, "
                "'Folders in the allowlist')")

    # Extraction is attempted *before* the placeholder check, and the order is load-bearing:
    # a genuine 44-character Drive id is random base64url and will occasionally contain a
    # sequence like "AAA". Diagnosing a working URL as a placeholder would be worse than any
    # message it replaced.
    if _ID_IN_PATH.search(candidate) or _ID_IN_QUERY.search(candidate):
        return None                                    # usable

    lowered = candidate.lower()
    for mark in PLACEHOLDER_MARKS:
        if mark.lower() in lowered:
            return (f"it contains {mark!r}, so it looks like a placeholder copied from "
                    f"documentation rather than a real link. Open the document and copy the "
                    f"URL from your browser's address bar")

    if "://" not in candidate and "/" not in candidate:
        return ("that looks like a bare file id rather than a URL. The allowlist needs the "
                "full URL — a link can be opened and checked by whoever reviews it, and a "
                "bare id cannot be told apart from a typo")

    host = (urlparse(candidate).netloc or "").lower()
    if any(host.endswith(g) for g in GOOGLE_HOSTS):
        if re.search(r"/d/?$", candidate):
            return ("the URL stops after '/d/', so the file id is missing. It should look "
                    "like .../document/d/<long-id>/edit")
        return ("it is a Google URL but has no '/d/<id>' segment. Copy the whole address "
                "from your browser while the document is open")
    if host:
        return (f"the host is {host!r}, which is not a Google Docs or Drive address. Expected "
                f"one of: {', '.join(GOOGLE_HOSTS)}")
    return ("it is not a Google document URL. Expected something like "
            "https://docs.google.com/document/d/<id>/edit")


def diagnose_setting(variable: str, value: str | None, default_path: str) -> str:
    """Why a whole configuration field yields nothing — the fail-closed case.

    Distinguishing "unset" from "set but empty" matters: they look identical in behaviour and
    have completely different fixes. One means nobody configured it; the other usually means a
    template was filled in with a blank, or a shell expanded an undefined variable to nothing.
    """
    if value is None:
        return f"{variable} is not set, and there is no file at {default_path}."
    if not value.strip():
        return (f"{variable} is set but empty — which is not the same as unset. If it came "
                f"from a config template or an unexpanded shell variable, that is the thing "
                f"to fix rather than this.")
    return f"{variable} yielded no usable entries."


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
    problem = diagnose_url(text)
    if problem is not None:
        raise AllowlistError(f"{text.strip()!r}: {problem}")
    found = _ID_IN_PATH.search(text) or _ID_IN_QUERY.search(text)
    if found is None:
        # Unreachable while `diagnose_url` and the two patterns agree — but not an `assert`:
        # under `python -O` an assert vanishes and this becomes an AttributeError on None,
        # which is a worse failure than the one it was guarding against.
        raise AllowlistError(
            f"{text.strip()!r}: no file id could be extracted, though it passed validation. "
            f"This is a bug in the allowlist parser, not in your configuration.")
    return found.group(1)


def parse_allowlist(text: str, *, source: str = "<string>") -> Listing:
    """Parse the allowlist format. Every malformed line is reported, not just the first.

    Reporting all of them matters: an operator fixing a curated list of thirty URLs should
    not have to run the server thirty times to find the thirty typos.

    A line of `*` means *every file*, and short-circuits the rest. It logs a warning, because
    the whole point of this file is that unrestricted access should be visible.
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

        if url.strip().lower() in ALL_SYNONYMS:
            log.warning("allowlist %s:%d grants access to EVERY file the credentials can "
                        "reach (%r)%s", source, number, url.strip(),
                        f": {reason}" if reason else "")
            return Listing(all_files=True)

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
            f"empty allowlist, because that is indistinguishable from a typo. Use a line "
            f"containing just `*` if unrestricted access is genuinely what you want.")
    return Listing(all_files=False, entries=tuple(entries))


def is_inline(value: str) -> bool:
    """Is this configuration value a list of URLs rather than a path?

    `://` is the discriminator: a URL always has it and a filesystem path does not. Chosen
    over a second environment variable so there is one place to look, and over guessing by
    `os.path.exists` — which would silently reinterpret a mistyped path as a URL list.
    """
    return "://" in value


def parse_inline(value: str, *, source: str = "inline") -> Listing:
    """Parse URLs given directly in configuration.

    Newlines separate entries, so a JSON `env` value can use `\n` and keep the `# reason`
    comments. Commas, semicolons and whitespace also separate entries **when the value has no
    `#`** — that condition is what stops a separator and a comment fighting over the same
    character, and it means the ambiguous case is simply not reachable.
    """
    text = value if "#" in value else re.sub(r"[,;\s]+", "\n", value.strip())
    return parse_allowlist(text, source=source)


def load_allowlist(path: str) -> Listing:
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
    listing = parse_allowlist(text, source=str(resolved))
    log.info("allowlist loaded from %s: %s", resolved,
             "EVERY file" if listing.all_files else f"{len(listing.entries)} file(s)")
    return listing
