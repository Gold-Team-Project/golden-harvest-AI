def test_trim_text():
    from app.rag.service import _trim_text
    s = "a" * 200
    out = _trim_text(s, max_chars=50)

    assert len(out) <= 51
    assert out.endswith("…")

class DummyDoc:
    def __init__(self, metadata):
        self.metadata = metadata

def test_filter_docs_by_tags():
    from app.rag.service import _filter_docs_by_tags

    docs = [
        DummyDoc({"item_tags": ["사과"], "variety_tags": ["부사"]}),
        DummyDoc({"item_tags": ["배"], "variety_tags": []}),
    ]

    filtered = _filter_docs_by_tags(
        docs,
        item_name="사과",
        variety_name="부사",
        k=3
    )

    assert len(filtered) == 1
