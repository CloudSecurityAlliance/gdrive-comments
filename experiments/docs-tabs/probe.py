#!/usr/bin/env python3
"""Do multi-tab Google Docs read back completely?  (Answer, measured: no — see RESULTS.md.)

Creates a throwaway document, adds a second tab, puts a distinguishable marker in EACH, then reads
it back three ways. Trashes the document in a `finally`, so an exception still cleans up.

The two-marker design is the point. A first attempt put text only in tab 1, which cannot tell
"tab 2 is empty" from "tab 2 is truncated" — the same finding either way, and no evidence.

    CSA_GW_TOKEN=~/.csa_google_workspace/token.json python probe.py
"""
import json
import os
import sys

from googleapiclient.discovery import build

from csa_google_workspace import Workspace, auth

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")


def main() -> int:
    creds = auth.load_cached_credentials(TOKEN, read_only=False)
    ws = Workspace.from_credentials(creds)
    docs = build("docs", "v1", credentials=creds).documents()

    ref = ws.files.create("PROBE docs-tabs (safe to delete)", "document")
    fid = ref.id
    doc = ws.open(fid)
    print(f"created {fid}")
    try:
        doc.append_text("MARKER_TAB_ONE\n")
        reply = doc.batch_update([{"addDocumentTab": {}}])
        tab2 = reply["replies"][0]["addDocumentTab"]["tabProperties"]["tabId"]
        print(f"added tab {tab2}")
        # Writing into a SPECIFIC tab needs tabId inside `location`.
        doc.batch_update([{"insertText": {"location": {"index": 1, "tabId": tab2},
                                          "text": "MARKER_TAB_TWO\n"}}])

        def markers(payload) -> str:
            blob = json.dumps(payload)
            return (("ONE" if "MARKER_TAB_ONE" in blob else "---") + " " +
                    ("TWO" if "MARKER_TAB_TWO" in blob else "---"))

        plain = docs.get(documentId=fid).execute()
        tabbed = docs.get(documentId=fid, includeTabsContent=True).execute()

        print(f"  get() default            : {markers(plain)}   tabs key: {'tabs' in plain}")
        print(f"  get(includeTabsContent)  : {markers(tabbed)}   tabs key: {'tabs' in tabbed}")
        print(f"  top-level body populated with the flag: "
              f"{bool(tabbed.get('body', {}).get('content'))}")
        print(f"  library as_text()        : {doc.as_text()!r}")

        # replaceAllText has an OPTIONAL tabsCriteria; omitting it should reach every tab.
        changed = doc.replace_text("MARKER", "REPLACED")
        print(f"  replace_text occurrences_changed: {changed}  (2 == it reached both tabs)")
        return 0
    finally:
        ws.files.trash(fid)
        print(f"trashed {fid}")


if __name__ == "__main__":
    sys.exit(main())
