"""Ask Drive itself which export/import conversions exist, instead of trusting docs.

`about.get(fields="exportFormats,importFormats")` is the authoritative matrix: it is what
the server will actually honour for `files.export` and for conversion on `files.create`.
Reads no document content, so it is safe to run against a real account.

    python experiments/export-formats/probe.py
"""
import sys

from googleapiclient.discovery import build

from csa_google_workspace.auth import load_cached_credentials

GOOGLE = "application/vnd.google-apps."
KINDS = ("document", "spreadsheet", "presentation", "drawing", "form", "site")


def main(token="~/.csa_google_workspace/token.json"):
    creds = load_cached_credentials(token, read_only=True)
    about = build("drive", "v3", credentials=creds).about().get(
        fields="exportFormats,importFormats").execute()

    print("## export: Google type -> what you can ask files.export for\n")
    for kind in KINDS:
        formats = about["exportFormats"].get(GOOGLE + kind)
        if formats:
            print(f"{kind} ({len(formats)})")
            for f in sorted(formats): print(f"    {f}")
            print()

    print("## import: upload type -> Google type it converts to\n")
    for source, targets in sorted(about["importFormats"].items()):
        google = [t.replace(GOOGLE, "") for t in targets if t.startswith(GOOGLE)]
        if google:
            print(f"{source:76s} -> {', '.join(google)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
