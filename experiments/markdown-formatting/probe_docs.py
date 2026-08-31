"""Does Markdown round-trip through a Google Doc, and does convert-on-UPDATE work?

Creates a throwaway document, writes Markdown, reads it back with `as_markdown()`, then replaces
the body via `files.update` with a `text/markdown` media body. Trashes the file in a `finally`.

See RESULTS.md. Answer: yes to both, at higher fidelity than expected.
"""
import io

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from csa_google_workspace import Workspace, auth

creds = auth.load_cached_credentials("~/.csa_google_workspace/token.json", read_only=False)
ws = Workspace.from_credentials(creds)
drive = build("drive", "v3", credentials=creds)

MD = """# Heading One

Some **bold** and *italic* text.

- first bullet
- second bullet

| Col A | Col B |
|---|---|
| 1 | 2 |
"""

print("=== 1. create with Markdown (known to work) ===")
ref = ws.files.create("PROBE md roundtrip (safe to delete)", "document", content=MD)
fid = ref.id; doc = ws.open(fid)
print("created:", fid)
try:
    back = doc.as_markdown()
    print("as_markdown() round trip:")
    for line in back.splitlines()[:14]:
        print("   ", repr(line))
    print()
    print("  heading survived :", "# Heading One" in back)
    print("  bold survived    :", "**bold**" in back)
    print("  bullets survived :", "- first bullet" in back or "* first bullet" in back)
    print("  table survived   :", "Col A" in back and "|" in back)

    print()
    print("=== 2. convert-on-UPDATE: replace the body with new Markdown ===")
    NEW = "# Replaced Heading\n\nCompletely **new** body.\n"
    media = MediaIoBaseUpload(io.BytesIO(NEW.encode()), mimetype="text/markdown",
                              resumable=False)
    drive.files().update(fileId=fid, media_body=media).execute()
    after = doc.as_markdown()
    print("  update accepted  : yes")
    print("  new heading there:", "Replaced Heading" in after)
    print("  old heading gone :", "Heading One" not in after)
finally:
    ws.files.trash(fid); print("\ntrashed:", fid)
