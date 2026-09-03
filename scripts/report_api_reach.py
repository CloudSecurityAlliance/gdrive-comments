#!/usr/bin/env python3
"""What can YOUR Google tenant reach? — a pasteable report, with no data in it.

This project covers **100% of the API endpoints it can see and test from its own tenant**, which
is not an enterprise-tier account. Some endpoints are therefore untested here, and we cannot
honestly say which are edition-gated, which need a domain admin, and which we simply have not
asked consent for — because **the first barrier masks the rest**: a missing scope refuses with
`insufficient authentication scopes` and hides whatever the next requirement would have been.

So the blocker on wider coverage is **verification, not code**. If you want coverage we do not
have, run this and paste the output into an issue. That single measurement is worth more than
any amount of our reasoning: this project has been wrong three times about what Google's
documentation says, and right every time it measured.

## WHAT THIS SENDS, AND WHAT IT DOES NOT

Written to be pasted into a **public** tracker, so it follows the rule `_environment.py` sets:
it reports **shapes, never content**.

  Reported:      method names, HTTP status codes, Google's error `status` and `reason`,
                 whether a boolean capability is on, counts, your Workspace *edition signals*.
  NEVER reported: file ids, file names, document text, comment text, email addresses,
                 domain names, your access token, filesystem paths, drive names.

Read it before you run it — that is the point of it being short.

## SAFETY

**Every call here is a READ**, and every listing asks for one item. Nothing is created, modified,
shared, trashed or deleted. It is safe to run against a production tenant, which is the only kind
of tenant that can answer the question.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

from csa_google_workspace import __version__  # noqa: E402
from csa_google_workspace.auth import load_cached_credentials  # noqa: E402

TOKEN = os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json")

# Read-only probes, each asking for the smallest possible answer. The point is the REFUSAL
# SHAPE, not the payload - so nothing here reads a document, and a success is reported as the
# word "reachable" rather than as anything it returned.
PROBES = [
    ("drive.about.get", "drive", "v3",
     lambda s: s.about().get(fields="kind")),
    ("drive.drives.list", "drive", "v3",
     lambda s: s.drives().list(pageSize=1, fields="kind")),
    ("drive.files.list", "drive", "v3",
     lambda s: s.files().list(pageSize=1, fields="kind")),
    ("drive.changes.getStartPageToken", "drive", "v3",
     lambda s: s.changes().getStartPageToken()),
    ("drive.apps.list", "drive", "v3",
     lambda s: s.apps().list(fields="kind")),
    # The interesting ones: present in the discovery document, and often unreachable.
    ("drive.approvals.list", "drive", "v3",
     lambda s: s.approvals().list(fileId="x", pageSize=1)),
    ("drivelabels.labels.list", "drivelabels", "v2",
     lambda s: s.labels().list(pageSize=1)),
    ("driveactivity.activity.query", "driveactivity", "v2",
     lambda s: s.activity().query(body={"pageSize": 1})),
    ("admin.users.list", "admin", "directory_v1",
     lambda s: s.users().list(customer="my_customer", maxResults=1)),
    ("vault.matters.list", "vault", "v1",
     lambda s: s.matters().list(pageSize=1)),
    ("cloudidentity.groups.list", "cloudidentity", "v1",
     lambda s: s.groups().list(pageSize=1)),
]


def classify(e: HttpError) -> str:
    """Google's refusal, reduced to a shape. No message text: it can name a file or a domain."""
    try:
        err = json.loads(e.content).get("error", {})
    except (ValueError, AttributeError):        # pragma: no cover
        return f"{e.resp.status} (unparseable)"
    status = err.get("status") or ""
    reason = ""
    details = err.get("errors") or []
    if details and isinstance(details, list):
        reason = details[0].get("reason", "")
    msg = str(err.get("message", "")).lower()
    # A curated set of causes, matched on WELL-KNOWN phrases only - never echoed verbatim,
    # because an error message can quote a file name or a domain.
    if "insufficient authentication scopes" in msg:
        hint = "needs a scope this client does not request"
    elif "has not been used in project" in msg or "is disabled" in msg:
        hint = "API not enabled in the Cloud project"
    elif "caller does not have permission" in msg or reason == "forbidden":
        hint = "permission denied (admin and/or edition)"
    elif e.resp.status == 404:
        hint = "not found (expected for a probe with a placeholder id)"
    else:
        hint = "see status"
    return f"{e.resp.status} {status or reason or '?'} - {hint}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    creds = load_cached_credentials(TOKEN, read_only=False)
    # SHAPE ONLY: how many scopes and their short names, never the token.
    scopes = sorted(s.rsplit("/", 1)[-1] for s in (getattr(creds, "scopes", None) or []))

    rows = []
    for name, api, ver, call in PROBES:
        try:
            svc = build(api, ver, credentials=creds, cache_discovery=False)
        except Exception as e:                  # noqa: BLE001 - report and continue
            rows.append((name, f"client build failed: {type(e).__name__}"))
            continue
        try:
            call(svc).execute()
            rows.append((name, "reachable"))
        except HttpError as e:
            rows.append((name, classify(e)))
        except Exception as e:                  # noqa: BLE001
            rows.append((name, f"error: {type(e).__name__}"))

    # Edition signals: booleans about what this account may do. No identity, no names.
    signals = {}
    try:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        about = drive.about().get(
            fields="canCreateDrives,canCreateTeamDrives,appInstalled,maxUploadSize").execute()
        signals = {k: about.get(k) for k in
                   ("canCreateDrives", "canCreateTeamDrives", "appInstalled", "maxUploadSize")}
    except Exception:                           # noqa: BLE001
        signals = {"about.get": "unreachable"}

    report = {
        "csa_google_workspace": __version__,
        "python": platform.python_version(),
        "platform": platform.system(),
        "scopes_held": scopes,
        "edition_signals": signals,
        "reach": dict(rows),
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("### API reach report — csa-google-workspace\n")
    print(f"  version {__version__} · python {platform.python_version()} · {platform.system()}")
    print(f"  scopes held ({len(scopes)}): {', '.join(scopes) or '(none reported)'}\n")
    print("  edition signals")
    for k, v in signals.items():
        print(f"    {k:<22} {v}")
    print("\n  reach")
    for name, outcome in rows:
        print(f"    {name:<34} {outcome}")
    print("\nPaste the whole of the above into an issue. It contains no file ids, no names,")
    print("no email addresses and no document content - check it yourself before sending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
