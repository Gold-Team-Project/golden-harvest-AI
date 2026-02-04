import pytest

def test_require_env_missing(monkeypatch):
    monkeypatch.delenv("MDB_HOST", raising=False)

    from app.document.services.data_service import _require_env
    with pytest.raises(RuntimeError):
        _require_env("MDB_HOST")

def test_get_data_for_inbound(monkeypatch):
    from app.document.schemas.documents import DocumentIntent, DocumentType
    from app.document.services.data_service import get_data_for_intent

    monkeypatch.setattr(
        "app.document.services.data_service.fetch_inbound_from_db",
        lambda *args, **kwargs: [
            {"inbound_date": "2025-01-01", "sku_no": "A", "quantity": 10}
        ]
    )
    monkeypatch.setattr(
        "app.document.services.data_service.build_inbound_excel",
        lambda base, items: {"items": items}
    )

    intent = DocumentIntent(
        document_type=DocumentType.INBOUND,
        start_date="2025-01-01",
        end_date="2025-01-31"
    )

    result = get_data_for_intent(intent)
    assert result["items"][0]["qty"] == 10
