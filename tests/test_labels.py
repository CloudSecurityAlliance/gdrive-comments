"""What a document is classified as — and never claiming it is unclassified when it is not.

Drive splits this across two APIs: `files.listLabels` says WHICH labels are on a file, as opaque
ids, and only the separate Drive Labels API can say what those ids are called. So `doc.labels`
is a join, and the interesting behaviour is what happens when the second half fails.

**The direction that matters.** Names can be unavailable for two reasons — the API is not enabled
in the Cloud project, or the token predates the `drive.labels.readonly` scope. In both cases the
ids are still true, so failing the call would throw away real information, and reporting nothing
would say "this document is unlabelled" about a document that is labelled. That is the error
somebody acts on. So the labels come back with `name=None` and a reason, and **an id is never
presented as a name**.
"""
from __future__ import annotations

import pytest

from csa_google_workspace import Workspace
from csa_google_workspace.backend import FakeBackend
from csa_google_workspace.exceptions import AccessError, NotFoundError, ServiceDisabledError
from csa_google_workspace.labels import build_label

DOC = "doc1"
MIME = "application/vnd.google-apps.document"

APPLIED = {
    "id": "LBL1", "revisionId": "3",
    "fields": {
        "fSel": {"valueType": "selection", "selection": ["chConf"]},
        "fTxt": {"valueType": "text", "text": ["Matter 4471"]},
        "fInt": {"valueType": "integer", "integer": [0]},
    },
}

DEFINITION = {
    "id": "LBL1",
    "properties": {"title": "Sensitivity", "description": "How to handle this"},
    "fields": [
        {"id": "fSel", "properties": {"displayName": "Level"},
         "selectionOptions": {"choices": [
             {"id": "chConf", "properties": {"displayName": "Confidential"}},
             {"id": "chPub", "properties": {"displayName": "Public"}}]}},
        {"id": "fTxt", "properties": {"displayName": "Matter"}},
        {"id": "fInt", "properties": {"displayName": "Retention years"}},
    ],
}


def doc(*, definitions=DEFINITION, applied=APPLIED, raises=None):
    backend = FakeBackend(
        {DOC: {"id": DOC, "name": "A Doc", "mimeType": MIME}},
        file_labels={DOC: [applied]} if applied else {DOC: []},
        label_definitions={"LBL1": definitions} if definitions else {})
    if raises is not None:
        def boom(label_id):
            raise raises
        backend.get_label_definition = boom
    return Workspace(backend).open(DOC)


class TestNamesWhenBothApisAnswer:
    def test_the_label_has_its_title(self):
        label = doc().labels[0]
        assert label.name == "Sensitivity" and label.resolved

    def test_a_selection_value_resolves_to_the_choice_name(self):
        """The point of the whole exercise: `chConf` on its own is unreadable, and
        `Confidential` is the answer somebody asked for."""
        level = [f for f in doc().labels[0].fields if f.id == "fSel"][0]
        assert level.name == "Level" and level.values == ["Confidential"]

    def test_a_text_value_comes_through_as_written(self):
        matter = [f for f in doc().labels[0].fields if f.id == "fTxt"][0]
        assert matter.values == ["Matter 4471"]

    def test_a_zero_survives(self):
        """#161: `str(v or "")` turns a legitimate 0 into an absence. A retention field of 0
        years means something quite different from a retention field left blank."""
        years = [f for f in doc().labels[0].fields if f.id == "fInt"][0]
        assert years.values == ["0"]

    def test_fields_are_ordered_deterministically(self):
        """Drive sends fields as a dict. Iterating it unsorted makes the output order depend on
        insertion, so two identical documents can render differently."""
        assert [f.id for f in doc().labels[0].fields] == ["fInt", "fSel", "fTxt"]

    def test_display_is_the_name_when_there_is_one(self):
        assert doc().labels[0].display == "Sensitivity"


class TestWhenTheSecondApiCannotAnswer:
    """The labels are still real. The names are not available. Both facts must survive."""

    @pytest.mark.parametrize("error,expect", [
        (ServiceDisabledError(service="drivelabels.googleapis.com", activation_url="http://x"),
         "not enabled"),
        (AccessError("insufficient permission"), "drive.labels.readonly"),
        (NotFoundError("gone"), "no longer exists"),
    ])
    def test_the_label_still_comes_back_with_a_reason(self, error, expect):
        labels = doc(raises=error).labels
        assert len(labels) == 1, "a file with a label must never report as unlabelled"
        assert labels[0].id == "LBL1"
        assert labels[0].name is None and not labels[0].resolved
        assert expect in labels[0].unresolved_reason

    def test_the_two_fixable_causes_are_told_apart(self):
        """An operator who reads "enable the API" when the real problem is a stale token will
        enable the API and still see no names. Different fixes, different messages."""
        disabled = doc(raises=ServiceDisabledError(service="s", activation_url="u"))
        missing = doc(raises=AccessError("nope"))
        assert disabled.labels[0].unresolved_reason != missing.labels[0].unresolved_reason
        assert "Enable" in disabled.labels[0].unresolved_reason
        assert "Sign in again" in missing.labels[0].unresolved_reason

    def test_an_id_is_never_presented_as_a_name(self):
        """`bXlsYWJlbA` alone reads as a label somebody named that. The fallback has to be
        visibly a reference, not a title."""
        label = doc(raises=AccessError("nope")).labels[0]
        assert label.name is None, "the id must not be copied into the name"
        assert label.display == "label LBL1"

    def test_the_values_still_arrive_even_unresolved(self):
        """The applied values come from the FIRST API, which worked. Only their labels are
        missing, so dropping the values would discard information nobody lost."""
        label = doc(raises=AccessError("nope")).labels[0]
        matter = [f for f in label.fields if f.id == "fTxt"][0]
        assert matter.values == ["Matter 4471"]
        assert matter.name is None and matter.display_name == "field fTxt"

    def test_a_selection_stays_an_id_it_cannot_resolve_but_says_so(self):
        """Without the definition there are no choice names. `choice chConf` is honest;
        `chConf` would look like the value itself."""
        label = doc(raises=AccessError("nope")).labels[0]
        level = [f for f in label.fields if f.id == "fSel"][0]
        assert level.values == ["choice chConf"]


class TestTheEmptyCases:
    def test_a_file_with_no_labels_is_an_empty_list(self):
        assert doc(applied=None).labels == []

    def test_an_unlabelled_file_and_an_unresolvable_one_are_distinguishable(self):
        """The single most important distinction in this module. Both could naively render as
        "no classification shown", and only one of them means the document is unclassified."""
        assert doc(applied=None).labels == []
        assert len(doc(raises=AccessError("nope")).labels) == 1


class TestTheJoinItself:
    def test_build_label_without_a_definition_needs_no_backend(self):
        label = build_label(APPLIED, None, "because")
        assert label.id == "LBL1" and label.name is None
        assert label.unresolved_reason == "because"

    def test_a_resolved_label_carries_no_reason(self):
        """A reason present alongside a name would be contradictory, and a caller that renders
        `unresolved_reason` when set would show a warning about a label that resolved fine."""
        assert build_label(APPLIED, DEFINITION, "ignored").unresolved_reason is None

    def test_an_unknown_value_type_degrades_to_no_values(self):
        """Google can add a field type. Probing keys instead of reading `valueType` would make
        a new type silently pick up the wrong array; this reads the type first."""
        label = build_label({"id": "L", "fields": {"f": {"valueType": "quantum",
                                                         "text": ["not this"]}}}, None)
        assert label.fields[0].values == []
        assert label.fields[0].value_type == "quantum"

    def test_a_user_field_yields_the_address(self):
        label = build_label(
            {"id": "L", "fields": {"f": {"valueType": "user",
                                         "user": [{"emailAddress": "a@b.c"}]}}}, None)
        assert label.fields[0].values == ["a@b.c"]


class TestRepr:
    def test_it_omits_field_values(self):
        """A label TITLE is organisational vocabulary and safe to log. A text field's VALUE is
        not - it can hold a matter number, a client name, or free text somebody typed."""
        r = repr(doc().labels[0])
        assert "Matter 4471" not in r and "Confidential" not in r

    def test_it_keeps_what_a_reader_needs(self):
        r = repr(doc().labels[0])
        assert "LBL1" in r and "Sensitivity" in r and "resolved=True" in r

    def test_a_field_repr_omits_its_values_too(self):
        """`Label.__repr__` never recurses into fields, so this class needs the rule MORE than
        `Label` does rather than less: anything logging a field directly would otherwise print
        the matter number."""
        matter = [f for f in doc().labels[0].fields if f.id == "fTxt"][0]
        r = repr(matter)
        assert "Matter 4471" not in r
        assert "fTxt" in r and "Matter" in r, "the field's own NAME is safe and useful"
        assert "values=1" in r, "the count is what a log needs: is there a value at all?"


class TestItIsReadOnlyByConstruction:
    def test_there_is_no_write_method_on_the_mixin(self):
        """Not "disabled" - absent. This library never requests `drive.labels`, so there is no
        configuration in which a model can change a classification. Labels are what DLP and
        retention key on, so relabelling `Confidential` to `Public` would defeat a control
        rather than use one, and unlike a bad edit nobody sees a diff."""
        from csa_google_workspace.labels import LabelsMixin
        writes = [n for n in dir(LabelsMixin)
                  if any(w in n for w in ("set_", "add_", "apply_", "remove_", "modify_"))]
        assert writes == []

    def test_the_backend_protocol_has_no_label_write_either(self):
        from csa_google_workspace.backend import Backend
        assert not [n for n in dir(Backend) if "label" in n.lower() and "get" not in n
                    and "list" not in n]
