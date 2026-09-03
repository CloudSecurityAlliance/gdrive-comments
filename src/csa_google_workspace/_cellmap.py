"""Map Sheets comments to A1 cells by parsing exported XLSX comment XML.
Heuristic: no confident unique match -> no entry (caller yields location=None).
Uses defusedxml (not stdlib xml.etree): the XLSX comes from Google, but comment
text inside it is attacker-controllable, so we harden against XXE / billion-laughs."""
import io
import logging
import posixpath
import re
import zipfile
from collections import defaultdict

import defusedxml.ElementTree as ET

from .comments import Location

log = logging.getLogger(__name__)

# Defense-in-depth bounds on the XLSX parse path (SEC-1). Today the archive is
# Google-generated and export-capped ~10 MB, so these are ceilings for a future where the
# input source changes (upload/import, a different backend) and a decompression bomb or a
# hostile comment volume becomes reachable. ZipInfo.file_size is read from the archive
# header, so an oversized member is rejected *before* it is decompressed.
_MAX_MEMBER_UNCOMPRESSED = 50 * 1024 * 1024    # 50 MB per persons/threadedComments member
_MAX_TOTAL_UNCOMPRESSED = 100 * 1024 * 1024    # 100 MB across all members read
_MAX_MEMBERS = 256                              # persons + threadedComments XML members

# The relationship namespace `r:id` lives in, and the suffix of the relationship TYPE that
# points a worksheet at its threaded comments. Matched by suffix because Microsoft has revised
# the date segment (`office/2017/10/...`) before and the trailing word is the stable part.
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_TC_REL_SUFFIX = "/threadedComment"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _second(ts: str) -> str:
    """Normalize 'dT' or Drive createdTime to 'YYYY-MM-DDTHH:MM:SS' (whole second, UTC)."""
    s = ts.replace("Z", "").replace("+00:00", "")
    return s.split(".")[0]


def location_from_ref(ref: str, tab: str | None = None) -> Location:
    """A1 reference -> Location. `tab` defaults to None: a caller that does not know the sheet
    must not have one invented for it (see `_sheet_names_by_comment_part`)."""
    m = re.match(r"([A-Za-z]+)(\d+)", ref or "")
    if not m:
        return Location(cell=ref, row=0, col=0, tab=tab)
    letters, row = m.group(1).upper(), int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return Location(cell=ref, row=row, col=col, tab=tab)


def column_letters(col: int) -> str:
    """Column number -> A1 letters. The inverse of the loop in `location_from_ref`.

    Base-26 **bijective**, not plain base-26: there is no zero digit, so 26 is `Z` and 27 is
    `AA`. Writing it as ordinary base-26 gives `A@` for 26 and is the classic way to get this
    wrong — hence `divmod(col - 1, 26)` rather than `divmod(col, 26)`.
    """
    out = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _resolve(base_dir: str, target: str) -> str:
    """An OPC relationship Target resolved to a zip member path.

    Targets are relative to the *directory of the part that declares them*, so a worksheet's
    `../threadedComments/threadedComment1.xml` means `xl/threadedComments/...`. Used
    unnormalised as a zip key it matches nothing and the tab silently comes back None.
    """
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(base_dir, target))


def _sheet_names_by_comment_part(read_named) -> dict[str, str]:
    """threadedComments part path -> the sheet TITLE that references it (#290).

    Three hops through the relationship graph, and each one is load-bearing:

        xl/workbook.xml             <sheet name="Sheet1" r:id="rId5"/>
        xl/_rels/workbook.xml.rels  rId5 -> worksheets/sheet1.xml
        xl/worksheets/_rels/sheet1.xml.rels
                                    .../threadedComment -> ../threadedComments/thread...1.xml

    **The graph must be walked, not guessed.** A real Google export numbers the first sheet
    `rId5`, so neither the `r:id` nor the `threadedCommentN.xml` index tracks sheet position;
    pairing them up by number happens to work on a one-sheet file and breaks silently on real
    ones (probed 2026-08-31).

    Returns only what it could resolve. **A part missing from the result means "sheet unknown",
    which is not the same as "the first sheet"** - see `parse_xlsx_comments` for why an absent
    tab must never be filled with a plausible default.
    """
    workbook = read_named("xl/workbook.xml")
    package = read_named("xl/_rels/workbook.xml.rels")
    if workbook is None or package is None:
        return {}

    titles: dict[str, str] = {}                       # r:id -> sheet title
    for el in workbook.iter():
        if _local(el.tag) != "sheet":
            continue
        rid, name = el.get(f"{{{_R_NS}}}id") or el.get("id"), el.get("name")
        if rid and name:
            titles[rid] = name

    sheet_parts: dict[str, str] = {}                  # sheet part path -> sheet title
    for el in package.iter():
        if _local(el.tag) != "Relationship":
            continue
        rid, target = el.get("Id"), el.get("Target")
        if rid in titles and target:
            sheet_parts[_resolve("xl", target)] = titles[rid]

    out: dict[str, str] = {}
    for part, title in sheet_parts.items():
        directory = posixpath.dirname(part)
        rels = read_named(posixpath.join(directory, "_rels", posixpath.basename(part) + ".rels"))
        if rels is None:
            continue                                  # a sheet whose rels we cannot read
        for el in rels.iter():
            if _local(el.tag) != "Relationship":
                continue
            target = el.get("Target")
            # A sheet with no comments has NO threadedComment relationship at all - real
            # exports carry only a drawing there. Absence is normal, not an error.
            if target and (el.get("Type") or "").endswith(_TC_REL_SUFFIX):
                out[_resolve(directory, target)] = title
    return out


def parse_xlsx_comments(xlsx_bytes: bytes) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    budget = _MAX_TOTAL_UNCOMPRESSED
    members = 0

    def _read(zinfo: zipfile.ZipInfo) -> bytes | None:
        """Read a member only if it stays within the per-member / total / count bounds;
        otherwise skip it (best-effort mapping degrades, never OOMs)."""
        nonlocal budget, members
        if members >= _MAX_MEMBERS:
            log.warning("XLSX comment parse hit the %d-member cap; skipping %s", _MAX_MEMBERS, zinfo.filename)
            return None
        if zinfo.file_size > _MAX_MEMBER_UNCOMPRESSED or zinfo.file_size > budget:
            log.warning("XLSX member %s (%d bytes) exceeds the parse size budget; skipping",
                        zinfo.filename, zinfo.file_size)
            return None
        members += 1
        budget -= zinfo.file_size
        return z.read(zinfo)

    def _read_named(name: str):
        """Parsed XML for a member, or None for absent / over-budget / malformed.

        Everything the relationship walk reads goes through here, so a damaged or missing
        graph costs the TAB and never the cell. Failing an export over a sheet name would
        trade the valuable half of the mapping for the decorative one.
        """
        try:
            zinfo = z.getinfo(name)
        except KeyError:
            return None
        data = _read(zinfo)
        if data is None:
            return None
        try:
            return ET.fromstring(data)
        except Exception:                   # noqa: BLE001 - malformed XML is not our problem
            log.warning("could not parse %s while resolving sheet names; tab will be None", name)
            return None

    sheet_by_part = _sheet_names_by_comment_part(_read_named)

    persons: dict[str, str] = {}
    for zinfo in z.infolist():
        name = zinfo.filename
        if "/persons/" in name and name.endswith(".xml"):
            data = _read(zinfo)
            if data is None:
                continue
            for el in ET.fromstring(data).iter():
                if _local(el.tag) == "person":
                    persons[el.get("id")] = el.get("displayName")
    roots: list[dict] = []
    for zinfo in z.infolist():
        name = zinfo.filename
        if "/threadedComments/" in name and name.endswith(".xml"):
            data = _read(zinfo)
            if data is None:
                continue
            for el in ET.fromstring(data).iter():
                if _local(el.tag) != "threadedComment" or el.get("parentId"):
                    continue
                text = ""
                for child in el:
                    if _local(child.tag) == "text":
                        text = "".join(child.itertext())
                roots.append({
                    "ref": el.get("ref"),
                    "author": persons.get(el.get("personId")),
                    "text": text,
                    "second": _second(el.get("dT", "")),
                    # None when the relationship graph could not be walked. NEVER a fallback
                    # to the first sheet: on a two-tab workbook that is a coin flip presented
                    # as a fact, which is the `list_labels` mistake in a different module.
                    "sheet": sheet_by_part.get(name),
                })
    return roots


def match_locations(comments, roots) -> dict:
    index = defaultdict(list)
    for r in roots:
        index[(r["author"], r["text"], r["second"])].append(r)
    out = {}
    for c in comments:
        author = c.author.display_name if c.author else None
        second = _second(c.created_time.isoformat()) if c.created_time else ""
        cands = index.get((author, c.content, second), [])
        if len(cands) == 1:                     # confident unique match only
            # The tab rides along on the matched entry. It does NOT participate in the match:
            # a Drive comment carries no sheet, so a tie between two entries on different tabs
            # is still a tie - see tests/test_cellmap_tabs.py::TestTheTabDoesNotBreakTies.
            out[c.id] = location_from_ref(cands[0]["ref"], tab=cands[0].get("sheet"))
    return out
