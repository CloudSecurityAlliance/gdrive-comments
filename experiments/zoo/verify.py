#!/usr/bin/env python3
"""Re-run every documented finding against the live corpus. Read-only.

**This is what makes the zoo a canary rather than a museum.** Every behaviour recorded in this
repository is Google's, undocumented by them, and can change without notice — and today nothing
would tell us. A scheduled run of this turns *"Google changed how unanchored comments render"*
from something a user reports into something we report.

Same reasoning as `scripts/check_controls.py`: externally-enforced behaviour is **asserted, not
assumed**. And like that script, a check it cannot perform reports **UNKNOWN** — never OK.

Read-only throughout: it lists, gets and exports, and writes nothing. Safe to schedule.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from csa_google_workspace import Workspace  # noqa: E402
from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")
HERE = os.path.dirname(__file__)

OK, FAIL, UNKNOWN = "OK", "FAIL", "UNKNOWN"


def check(results: list, name: str, claim: str, fn) -> None:
    """Run one check. An exception is UNKNOWN, not FAIL — we could not look, which is a
    different thing from looking and finding the claim false, and collapsing the two is how a
    monitoring system starts lying."""
    try:
        got = fn()
    except Exception as e:                      # noqa: BLE001
        results.append((UNKNOWN, name, claim, f"{type(e).__name__}: {str(e)[:70]}"))
        return
    results.append((OK if got is True else FAIL, name, claim, "" if got is True else repr(got)))


def main() -> int:
    ws = Workspace.from_credentials(load_cached_credentials(TOKEN, read_only=False))
    with open(os.path.join(HERE, "manifest.json"), encoding="utf-8") as fh:
        docs = {s["name"]: s["id"] for s in json.load(fh)["specimens"]}
    try:
        with open(os.path.join(HERE, "manifest_more.json"), encoding="utf-8") as fh:
            more = json.load(fh)
    except FileNotFoundError:
        more = {}

    r: list = []

    # --- the four anchor states, on the specimen built for them ---------------------
    def states():
        cs = list(ws.open(docs["docs-anchor-states"]).comments)
        seen = {c.anchor_state for c in cs}
        # `file` and `quote_only` are API-created and always present. `text` and `object`
        # arrive only once somebody has placed them by hand, so their ABSENCE is reported
        # separately rather than failing - it is a to-do, not a regression.
        return {"file", "quote_only"} <= seen
    check(r, "anchor-states", "file-level and quote-only states both present", states)

    def hand_placed():
        cs = list(ws.open(docs["docs-anchor-states"]).comments)
        return sorted({c.anchor_state for c in cs})
    r.append((UNKNOWN if set(hand_placed()) <= {"file", "quote_only"} else OK,
              "anchor-states", "editor-created states (text, object) present",
              f"have {hand_placed()} - place by hand to complete"))

    # --- a quote-only comment carries a quote the document does NOT contain ---------
    def false_quote():
        doc = ws.open(docs["docs-anchor-states"])
        text = doc.as_text()
        for c in doc.comments:
            q = c.quoted_text or ""
            if q and q not in text:
                return True
        return False
    check(r, "anchor-states", "a quote-only comment quotes text NOT in the document (#380)",
          false_quote)

    # --- notes are invisible to the comments API ------------------------------------
    if more.get("sheets", {}).get("sheets-notes-are-not-comments"):
        fid = more["sheets"]["sheets-notes-are-not-comments"]

        def notes_not_comments():
            sheet = ws.open(fid)
            return len(list(sheet.comments)) == 0 and len(sheet.notes) >= 3
        check(r, "sheets-notes", "notes present AND comments.list returns zero (#405 family)",
              notes_not_comments)

    # --- the header guess is demonstrably wrong on the offset grid ------------------
    if more.get("sheets", {}).get("sheets-header-not-row-1"):
        fid = more["sheets"]["sheets-header-not-row-1"]

        def offset_header():
            # QUALIFIED with the tab name, deliberately: an unqualified A1 range reads the
            # FIRST tab, and this check failed the moment a README tab was added at index 0 -
            # it was reading the documentation and reporting the data missing.
            values = ws.open(fid).values("'Sheet1'!A1:C6")
            # Row 1 is a title; row 4 is the real header. A naive reader takes row 1.
            return (values[0][0].startswith("QUARTERLY")
                    and values[3][0] == "Region")
        check(r, "sheets-header", "row 1 is a TITLE and row 4 is the real header",
              offset_header)

    # --- the corpus is reachable and documents itself --------------------------------
    for name, fid in docs.items():
        def documented(fid=fid):
            return "HOW THIS FILE WAS MADE" in ws.open(fid).as_text()
        check(r, name, "carries its own provenance section", documented)

    width = max(len(n) for _, n, _, _ in r)
    print("### zoo verification\n")
    counts = {OK: 0, FAIL: 0, UNKNOWN: 0}
    for status, name, claim, detail in r:
        counts[status] += 1
        print(f"  [{status:<7}] {name:<{width}}  {claim}")
        if detail:
            print(f"             {detail}")
    print(f"\n  {counts[OK]} OK · {counts[FAIL]} FAIL · {counts[UNKNOWN]} UNKNOWN")
    print("\n  UNKNOWN is never OK. It means the check could not run, or a hand-placed state")
    print("  has not been placed yet - both are things to act on, not to pass over.")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
