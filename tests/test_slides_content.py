from csa_google_workspace import Workspace, _content
from csa_google_workspace.backend import FakeBackend

PRES = "application/vnd.google-apps.presentation"
META = {"p": {"id": "p", "name": "P", "mimeType": PRES, "webViewLink": "https://x/presentation/d/p/edit"}}


def _shape(text):
    return {"shape": {"text": {"textElements": [{"textRun": {"content": text}}]}}}


PRESENTATION = {"slides": [
    {"pageElements": [_shape("Title slide\n"), _shape("subtitle\n")]},
    {"pageElements": [_shape("Second slide\n")]},
]}


def slides():
    return Workspace(FakeBackend(META, presentations={"p": PRESENTATION})).open("p")


def test_slides_list_and_per_slide_text():
    s = slides().slides
    assert len(s) == 2
    assert "Title slide" in s[0].as_text() and "subtitle" in s[0].as_text()
    assert "Second slide" in s[1].as_text()


def test_deck_as_text_joins_all_slides():
    t = slides().as_text()
    assert "Title slide" in t and "Second slide" in t


def test_slide_notes():
    # Create a presentation with a slide containing speaker notes
    presentation_with_notes = {"slides": [
        {"pageElements": [_shape("Slide with notes\n")],
         "slideProperties": {"notesPage": {"pageElements": [
             {"shape": {"text": {"textElements": [{"textRun": {"content": "speaker note here"}}]}}}
         ]}}}
    ]}
    workspace = Workspace(FakeBackend(META, presentations={"p": presentation_with_notes}))
    slide_deck = workspace.open("p")
    assert "speaker note here" in slide_deck.slides[0].notes


def test_slide_shape_ids_lists_text_capable_shapes():
    pres = {"slides": [{"pageElements": [
        {"objectId": "box1", "shape": {"text": {"textElements": []}}},
        {"objectId": "box2", "shape": {}},                      # empty text box still targetable
        {"objectId": "img1", "image": {}},                      # not a shape -> excluded
        {"line": {}},                                            # no objectId -> excluded
    ]}]}
    deck = Workspace(FakeBackend(META, presentations={"p": pres})).open("p")
    assert deck.slides[0].shape_ids == ["box1", "box2"]


def test_slide_text_recurses_into_tables_and_element_groups():
    slide = {"pageElements": [
        _shape("shape text\n"),
        {"table": {"tableRows": [
            {"tableCells": [{"text": {"textElements": [{"textRun": {"content": "cell text"}}]}}]}
        ]}},
        {"elementGroup": {"children": [_shape("grouped text")]}},
    ]}
    text = _content.slide_text(slide)
    assert "shape text" in text
    assert "cell text" in text
    assert "grouped text" in text


def test_slide_exposes_its_own_page_object_id():
    """`Slide.object_id` is the PAGE id, as against the shapes on it (#433).

    Every create* request — `createShape`, `createTable`, `createImage` — takes a
    `pageObjectId`, so without this the public `Slides.batch_update` cannot target a slide
    and a caller has to reach into `_raw`. The live suite was doing exactly that, through the
    backend rather than the model, and broke when `PolicyBackend` began refusing it.
    """
    pres = {"slides": [
        {"objectId": "p", "pageElements": [{"objectId": "box1", "shape": {}}]},
        {"objectId": "g2d1a", "pageElements": []},
    ]}
    deck = Workspace(FakeBackend(META, presentations={"p": pres})).open("p")
    assert [s.object_id for s in deck.slides] == ["p", "g2d1a"]
    # and it is distinct from the shapes ON the slide, which is the whole point
    assert deck.slides[0].object_id not in deck.slides[0].shape_ids


def test_slide_object_id_is_none_when_absent_rather_than_raising():
    """A malformed page should not take the whole deck down — `slides` is a read path."""
    deck = Workspace(FakeBackend(META, presentations={"p": {"slides": [{}]}})).open("p")
    assert deck.slides[0].object_id is None
