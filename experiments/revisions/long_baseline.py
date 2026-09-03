#!/usr/bin/env python3
"""Do Google Doc revisions SURVIVE, when the edits are minutes apart rather than seconds?

The short-gap probe (2026-09-03) found that only revision 1 and the current head survive: every
intermediate revision was coalesced away within seconds. But 4-6 second gaps sit well inside
Docs' coalescing window, so that result cannot distinguish

  * "Drive exposes only two revisions for a Doc, ever"  -- which would make #389's read-a-past
    revision request very nearly vacuous, and reset-to-a-revision able to reach only the file's
    creation state, from
  * "rapid edits coalesce, and edits minutes apart each get their own durable revision"  --
    which makes the whole feature useful.

Everything about the request depends on which it is, so it is worth the wall-clock.

Edits are spaced `--gap` seconds apart (default 300 = 5 minutes) and the full revision list is
recorded after each one, so the output shows not just the final count but WHEN each revision
appeared and when it disappeared.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from googleapiclient.discovery import build  # noqa: E402

from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gap", type=int, default=300, help="seconds between edits")
    ap.add_argument("--edits", type=int, default=5)
    ap.add_argument("--keep", action="store_true", help="do not trash the document afterwards")
    args = ap.parse_args()

    creds = load_cached_credentials(TOKEN, read_only=False)
    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)

    fid = drive.files().create(
        body={"name": "PROBE revision durability (throwaway)",
              "mimeType": "application/vnd.google-apps.document"},
        fields="id").execute()["id"]
    print(f"doc: {fid}\ngap: {args.gap}s   edits: {args.edits}", flush=True)

    seen: dict[str, str] = {}          # revision id -> when we first saw it
    for n in range(1, args.edits + 1):
        docs.documents().batchUpdate(documentId=fid, body={"requests": [
            {"insertText": {"location": {"index": 1},
                            "text": f"Edit {n} at {time.strftime('%H:%M:%S')}.\n"}}]}).execute()
        time.sleep(8)                  # let Drive settle before reading the list
        revs = drive.revisions().list(
            fileId=fid, fields="revisions(id,modifiedTime,keepForever)").execute().get(
                "revisions", [])
        now = [r["id"] for r in revs]
        for r in now:
            seen.setdefault(r, f"after edit {n}")
        gone = [r for r in seen if r not in now]
        print(f"  edit {n}: revisions={now}  (disappeared since: {gone or 'none'})", flush=True)
        if n < args.edits:
            time.sleep(max(0, args.gap - 8))

    print(f"\nfirst seen: {json.dumps(seen, indent=2)}", flush=True)
    final = drive.revisions().list(
        fileId=fid, fields="revisions(id,modifiedTime,lastModifyingUser(displayName))").execute()
    print(f"final list ({len(final.get('revisions', []))}):", flush=True)
    for r in final.get("revisions", []):
        print(f"  {r['id']:<4} {r.get('modifiedTime')}", flush=True)
    print(f"\nVERDICT: {len(final.get('revisions', []))} revision(s) survive "
          f"{args.edits} edits spaced {args.gap}s apart.", flush=True)

    if args.keep:
        print(f"kept: https://docs.google.com/document/d/{fid}/edit", flush=True)
    else:
        drive.files().update(fileId=fid, body={"trashed": True}).execute()
        print(f"trashed {fid}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
