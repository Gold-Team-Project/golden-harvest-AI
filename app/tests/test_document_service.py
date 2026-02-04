def test_create_document(monkeypatch):
    from app.document.services.document_service import create_document

    monkeypatch.setattr(
        "app.document.services.document_service.get_data_for_intent",
        lambda intent: {"foo": "bar"}
    )
    monkeypatch.setattr(
        "app.document.services.document_service.generate_excel",
        lambda data: (b"123", "xlsx", "application/vnd.ms-excel")
    )

    class DummyIntent:
        document_type = type("T", (), {"name": "INBOUND"})

    result = create_document(DummyIntent())

    assert result["filename"].startswith("inbound_")
    assert result["mime_type"].startswith("application/")
