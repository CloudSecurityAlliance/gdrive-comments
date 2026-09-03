"""Seam guard: FakeBackend and ApiBackend must both satisfy the Backend Protocol with
matching method signatures (audit #14).

FakeBackend powers every unit test, so if a new Backend method is added to ApiBackend (or
the Protocol) but not FakeBackend — or a signature drifts — unit tests would exercise a
stale fake. This test fails loudly on that drift. (Behavioral parity for the real-Google
paths, e.g. error translation, is covered separately in test_apibackend_*.)
"""
import inspect

import pytest

from csa_google_workspace.backend import ApiBackend, Backend, FakeBackend


def _protocol_methods() -> set[str]:
    return {name for name, val in vars(Backend).items()
            if callable(val) and not name.startswith("_")}


def _params(func) -> list[tuple[str, bool]]:
    """(name, has_default) for each parameter except self — annotations ignored, since the
    Protocol is annotated and the concrete impls need not be."""
    sig = inspect.signature(func)
    return [(p.name, p.default is not inspect.Parameter.empty)
            for p in sig.parameters.values() if p.name != "self"]


def test_protocol_has_the_expected_surface():
    # sanity: catch accidental emptiness of the introspection
    methods = _protocol_methods()
    assert {"get_file_metadata", "list_comments", "create_comment",
            "sheets_values_append", "slides_batch_update"} <= methods


@pytest.mark.parametrize("impl", [FakeBackend, ApiBackend], ids=["FakeBackend", "ApiBackend"])
def test_impl_covers_protocol_with_matching_signatures(impl):
    for name in sorted(_protocol_methods()):
        assert hasattr(impl, name), f"{impl.__name__} is missing Backend.{name}"
        want = _params(getattr(Backend, name))
        got = _params(getattr(impl, name))
        assert got == want, f"{impl.__name__}.{name} params {got} != Protocol {want}"


def _public_methods(impl) -> set[str]:
    return {name for name, value in inspect.getmembers(impl)
            if not name.startswith("_")
            and (inspect.isfunction(value) or isinstance(value, property))}


@pytest.mark.parametrize("impl", [FakeBackend, ApiBackend], ids=["FakeBackend", "ApiBackend"])
def test_no_impl_has_a_public_method_the_protocol_does_not(impl):
    """THE REVERSE DIRECTION (#325). The check above walks Protocol -> impl, so an
    implementation-side addition with no Protocol counterpart passed silently.

    Latent when it was filed and still latent - both impls match exactly today. It is here
    because the two directions fail differently and only one of them was covered:

    **A `FakeBackend`-only method is the dangerous one.** Every unit test runs on the fake, so
    a method the real backend cannot perform would let the whole suite exercise a capability
    that does not exist - which is the "stale double" this file's own docstring exists to
    prevent, arriving from the other side.

    **An `ApiBackend`-only method** is a capability outside the seam. `policy._GATES` is keyed
    on these names and `PolicyBackend` fails closed on an unlisted one, so it would be refused
    rather than ungoverned - but a divergence nothing reports is one nobody fixes.

    Filed after the same shape turned up in the sibling `csa-skilljar` audit: a conformance
    test written in one direction is a habit, not a one-off.
    """
    extra = sorted(_public_methods(impl) - _protocol_methods())
    assert extra == [], (
        f"{impl.__name__} has public methods absent from the Backend Protocol: {extra}. Add "
        f"them to the Protocol (and to the other impl, and to policy._GATES), or make them "
        f"private - an implementation-only method is outside the seam every guard keys on.")
