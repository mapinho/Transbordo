import pathlib

import pytest

import data_loader


def test_source_no_longer_contains_hardcoded_credential():
    """Regression guard: the literal hardcoded local-dev password must never
    come back into the source (finding flagged in the Fase 1 report,
    data_loader.py:61, never assigned a tracked id -- fixed here)."""
    source = pathlib.Path(data_loader.__file__).read_text(encoding="utf-8")
    assert "Comigo36908" not in source


def test_get_engine_raises_clear_error_when_no_credentials_configured(monkeypatch):
    """With no st.secrets, no DB_* env vars, and not running in the cloud,
    get_engine() must fail loudly and explain how to configure .env --
    it must NOT silently fall back to a hardcoded credential."""
    for var in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME",
                "STREAMLIT_RUNTIME_ENV", "STREAMLIT_SERVER_PORT"):
        monkeypatch.delenv(var, raising=False)

    class _EmptySecrets(dict):
        def __bool__(self):
            return False

    monkeypatch.setattr(data_loader.st, "secrets", _EmptySecrets(), raising=False)

    with pytest.raises(ConnectionError) as exc_info:
        data_loader.get_engine.__wrapped__()

    message = str(exc_info.value)
    assert "Comigo36908" not in message
    assert ".env" in message
