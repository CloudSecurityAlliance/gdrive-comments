from csa_google_workspace import auth


def test_scopes_readwrite_include_all_four_services():
    s = auth.scopes_for(read_only=False)
    assert any(x.endswith("/auth/drive") for x in s)
    assert any(x.endswith("/auth/documents") for x in s)
    assert any(x.endswith("/auth/spreadsheets") for x in s)
    assert any(x.endswith("/auth/presentations") for x in s)


def test_the_only_readonly_scope_in_the_readwrite_set_is_labels():
    """This used to assert `not any(".readonly" in x)`, and that was right until labels.

    The rule it encoded - "read-write means no read-only scopes" - was a proxy for the real one,
    which is that a posture should not silently ask for less than it claims. `drive.labels` is
    the case that breaks the proxy without breaking the rule: it is requested read-only in BOTH
    postures ON PURPOSE, because labels are a CLASSIFICATION system that DLP and retention key
    on. Writing one is not an edit to a document, it is a claim about how the organisation must
    treat it, and a model that could relabel `Confidential` to `Public` would be defeating a
    control rather than using one.

    So the assertion is now specific rather than absolute: exactly one read-only scope, and it
    is that one. A second `.readonly` appearing here would be a narrowing nobody decided.
    """
    readonly = [x for x in auth.scopes_for(read_only=False) if ".readonly" in x]
    assert readonly == ["https://www.googleapis.com/auth/drive.labels.readonly"]


def test_scopes_readonly_are_all_readonly_variants():
    s = auth.scopes_for(read_only=True)
    assert all(x.endswith(".readonly") for x in s)
    assert len(s) == 5, "four services plus labels; was 4 before labels landed"


def test_labels_is_requested_in_both_postures():
    """It has no write form, so there is nothing to narrow. Asserted because the natural way to
    add a scope is inside the `_RW`/`_RO` pair, and doing that would have produced a
    `drive.labels` write scope in the read-write posture - the exact thing this must not ask
    for."""
    labels = "https://www.googleapis.com/auth/drive.labels.readonly"
    assert labels in auth.scopes_for(read_only=True)
    assert labels in auth.scopes_for(read_only=False)
    assert "https://www.googleapis.com/auth/drive.labels" not in auth.scopes_for(False), (
        "the WRITE labels scope must never be requested")


def test_needs_reconsent_true_when_scope_missing():
    granted = ["https://www.googleapis.com/auth/drive.readonly"]
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted, required) is True


def test_needs_reconsent_false_when_all_present():
    required = auth.scopes_for(read_only=False)
    assert auth.needs_reconsent(granted=required, required=required) is False


def test_needs_reconsent_false_when_granted_rw_satisfies_required_readonly():
    # A user who already authorized full RW scopes shouldn't be forced to re-consent
    # just because a later call opens with read_only=True.
    assert auth.needs_reconsent(granted=auth.scopes_for(False), required=auth.scopes_for(True)) is False


def test_needs_reconsent_false_when_readonly_satisfies_readonly():
    assert auth.needs_reconsent(granted=auth.scopes_for(True), required=auth.scopes_for(True)) is False


def test_needs_reconsent_true_when_scope_truly_missing():
    # granted lacks both the readonly variant and the RW base for "presentations" ->
    # still must reconsent even with the readonly-satisfied-by-RW fallback in place.
    granted = [s for s in auth.scopes_for(False) if "presentations" not in s]
    required = auth.scopes_for(read_only=True)
    assert auth.needs_reconsent(granted, required) is True
